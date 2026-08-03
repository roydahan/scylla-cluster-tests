# Mini-Plan: Prevent Orphaned Spot Fleet Instances on Provisioning Timeout (SCT-779)

**Date:** 2026-08-03
**Estimated LOC:** ~250
**Related Jira:** [SCT-779](https://scylladb.atlassian.net/browse/SCT-779)
**Reproduction:** https://argus.scylladb.com/tests/scylla-cluster-tests/57239065-71b4-4179-b38b-e8aaf40cc2fd

## Problem
On `scale-180-200-cluster-test`, the Jenkins "Provision Resources" stage (fixed 30-min timeout,
`vars/longevityPipeline.groovy:353`) fired while SCT was mid-relocation to a 3rd fallback AWS
region (`eu-west-3`). The hard-kill of the remote process meant `SCTProvisionAWSLayout`'s normal
`except (ClientError, ProvisioningCapacityExhausted)` cleanup path
(`sdcm/sct_provision/aws/layout.py:113-125`) never ran, so the in-flight Spot Fleet Request was
never cancelled. AWS kept fulfilling it asynchronously after the pipeline gave up, and the
post-actions `clean-resources` step (`sdcm/utils/resources_cleanup.py:clean_instances_aws`) only
takes a point-in-time instance snapshot — it has no code path that cancels open Spot Fleet/Spot
Instance Requests. Result: 66 orphaned `i7i.large` instances leaked in `eu-west-3`.

Per the user's direction, this plan replaces the "increase/adaptivize the stage timeout" idea
with an explicit, permanent opt-out of cross-region relocation for scale tests (since relocating
a 180+ node cluster across regions is what blew the time budget in the first place), plus the two
defense-in-depth code fixes for spot-fleet cleanup.

## Approach
1. **Disable region fallback for all scale-tests** (replaces original suggestion #1):
   Add `fallback_to_next_region: false` to `test-cases/scale/scale-cluster.yaml`, the shared base
   config included by every `configurations/scale/scale-*.yaml` variant. This stops scale tests
   from ever attempting the multi-region relocation loop that exceeded the stage timeout; a scale
   test will instead fail fast (AZ fallback within the single configured region still applies) and
   go through the normal in-process cleanup path, which is what already worked correctly for the
   `eu-west-1`/`eu-west-2` AZ-fallback attempts in this incident.
2. **Add a signal-based safety net around spot-fleet provisioning** so an external interruption
   (SIGTERM sent by the Jenkins/docker timeout, or Ctrl-C) still triggers spot fleet cancellation
   before the process exits, instead of relying solely on Python exception handling:
   - Register a `signal.signal(SIGTERM, handler)` / `try/finally` around
     `SCTProvisionAWSLayout._do_provision()` (`sdcm/sct_provision/aws/layout.py:366`) that calls a
     new `_cleanup_partial_provision()`-equivalent path even on forced termination.
   - Track in-flight Spot Fleet Request IDs (from `EC2ClientWrapper.create_spot_fleet`,
     `sdcm/ec2_client.py:345-413`) in `TestConfig`/a module-level registry keyed by `test_id` so the
     signal handler can find and cancel them without needing full instance-discovery state.
3. **Add explicit Spot Fleet/Spot Instance Request cancellation to `clean_cloud_resources`** as a
   defense-in-depth backstop (covers cases where step 2's in-process handler itself didn't run,
   e.g. SIGKILL / host reboot).

   **Correction from initial draft:** the SDK-wrapper cancel calls already exist today
   (`sdcm/ec2_client.py:246,410` and `sdcm/provision/aws/provisioner.py:225,237,294`), but they are
   only reachable from *inside the same in-process polling loop that created the request* (a local
   `request_id` variable, called only when that function itself returns/raises normally). There is
   no standalone/reusable "cancel by test_id" entry point callable from a separate process. Worse,
   `create_spot_fleet_instance_request` (`sdcm/provision/aws/utils.py:302-317`) builds the
   `SpotFleetRequestConfigDataTypeDef` **without any top-level `TagSpecifications`** — only the
   *instances* the fleet launches get tagged (`ResourceType="instance"` inside
   `LaunchSpecifications`), never the Spot Fleet Request resource itself. So a later, separate
   `clean-resources` invocation cannot `describe_spot_fleet_requests` and filter by `TestId` tag —
   **the request ID must be persisted somewhere durable at creation time** for a later process to
   find it. `sdcm/test_config.py` already solves an equivalent cross-process handoff problem for
   region/AZ relocation via `write_resolved_placement()` / `read_resolved_placement()`
   (`sdcm/test_config.py:161-232`), which persist to a fixed path
   `base_logdir()/<test_id>/resolved_placement.yaml` on the (persistent, single) SCT Runner
   instance — surviving across the separate `./sct.py provision-resources`, `./sct.py collect-logs`,
   `./sct.py clean-resources` invocations. Reuse this exact pattern instead of inventing a new one:
   - Add `TestConfig.write_spot_fleet_request(test_id, region_name, request_id)`,
     `TestConfig.read_spot_fleet_requests(test_id)`, and
     `TestConfig.delete_spot_fleet_requests(test_id)` classmethods in `sdcm/test_config.py`,
     modeled on `write_resolved_placement`/`read_resolved_placement`/`delete_resolved_placement`,
     persisting to `base_logdir()/<test_id>/spot_fleet_requests.yaml` (append-only list of
     `{request_id, region_name}` entries, since a single test can create multiple fleet requests
     across AZ/region retries).
   - Call `TestConfig.write_spot_fleet_request(...)` right after `request_spot_fleet` succeeds in
     both `sdcm/ec2_client.py:_request_spot_fleet` and
     `sdcm/provision/aws/utils.py:create_spot_fleet_instance_request`, and remove the entry (or mark
     it cancelled) once the existing in-process `cancel_spot_fleet_requests(...)` call succeeds —
     so only requests that were *never* cleanly cancelled remain in the file.
   - New helper `cancel_leaked_spot_fleet_requests(test_id, dry_run)` in
     `sdcm/utils/resources_cleanup.py` that reads `TestConfig.read_spot_fleet_requests(test_id)`
     and, for each `{request_id, region_name}` still present, calls
     `describe_spot_fleet_requests(SpotFleetRequestIds=[request_id])` in that region; if the request
     state is anything other than terminated/cancelled, call
     `cancel_spot_fleet_requests(SpotFleetRequestIds=[request_id], TerminateInstances=True)`.
   - Wire it into `clean_cloud_resources()` (`sdcm/utils/resources_cleanup.py:157-171`) as a new
     `cleanup_step("AWS leaked spot fleet requests")`, run *before* `clean_instances_aws` so any
     instances launched by a still-active request during the cleanup window are also picked up by
     a subsequent instance-cleanup pass (loop the instance-cleanup + cancel pair once more if any
     requests were found active, to catch stragglers).
4. Add unit tests for the new `TestConfig` persistence helpers and the cancellation helper, plus a
   regression test confirming `fallback_to_next_region` resolves to `False` for the scale test
   config.

## Files to Modify
- `test-cases/scale/scale-cluster.yaml` -- add `fallback_to_next_region: false`
- `sdcm/sct_provision/aws/layout.py` -- add SIGTERM/`finally`-based cleanup around
  `_do_provision()` (new method, e.g. `_do_provision_with_interrupt_guard()`), reuse existing
  `_cleanup_partial_provision()`
- `sdcm/test_config.py` -- add `write_spot_fleet_request()`, `read_spot_fleet_requests()`,
  `delete_spot_fleet_requests()` classmethods (modeled on the existing
  `write_resolved_placement`/`read_resolved_placement`/`delete_resolved_placement` at lines
  161-232), persisting to `base_logdir()/<test_id>/spot_fleet_requests.yaml`
- `sdcm/ec2_client.py` -- call `TestConfig.write_spot_fleet_request(...)` right after
  `_request_spot_fleet` returns a `SpotFleetRequestId` (`_request_spot_fleet`, line ~126-166);
  clear/mark-cancelled the entry once the existing inline `cancel_spot_fleet_requests` calls
  (lines 246, 410) succeed
- `sdcm/provision/aws/utils.py` -- same registration in `create_spot_fleet_instance_request`
  (lines 302-317)
- `sdcm/provision/aws/provisioner.py` -- clear the registered entry once the existing inline
  `cancel_spot_fleet_requests` calls (lines 225, 237, 294) succeed
- `sdcm/utils/resources_cleanup.py` -- new `cancel_leaked_spot_fleet_requests(test_id, dry_run)`
  helper; wire into `clean_cloud_resources()` (lines 157-171) as a new cleanup step run before
  `clean_instances_aws`
- `unit_tests/unit/test_clean_cloud_resources_func.py` -- add tests for
  `cancel_leaked_spot_fleet_requests()` (mocked boto3 `describe_spot_fleet_requests` /
  `cancel_spot_fleet_requests`, and a mocked/tmp-path-based `TestConfig` persistence file)
- `unit_tests/unit/test_config.py` (or nearest existing `TestConfig` test) -- add tests for
  `write_spot_fleet_request` / `read_spot_fleet_requests` / `delete_spot_fleet_requests`, and
  assert `SCTConfiguration` resolves `fallback_to_next_region=False` when loading
  `test-cases/scale/scale-cluster.yaml`

## Verification
- [ ] `uv run sct.py output-conf -b aws --test-config test-cases/scale/scale-cluster.yaml` shows
      `fallback_to_next_region: false`
- [ ] Unit tests pass: `uv run python -m pytest unit_tests/unit/test_clean_cloud_resources_func.py -v`
- [ ] Unit tests pass: `uv run python -m pytest unit_tests/unit/test_config.py -v` (new
      `spot_fleet_requests` persistence tests)
- [ ] Manual/staged test: simulate a `SIGTERM` during a mocked spot-fleet `_wait_for_fleet_request_done`
      poll and confirm `cancel_spot_fleet_requests` is invoked
- [ ] Manual/staged test: pre-populate a `spot_fleet_requests.yaml` fixture with a fake
      `{request_id, region_name}` entry, run `clean-resources` for that test-id, and confirm
      `cancel_spot_fleet_requests(TerminateInstances=True)` is called and the persisted file is
      cleared
- [ ] `uv run sct.py pre-commit` passes
