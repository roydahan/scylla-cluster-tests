# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright (c) 2020 ScyllaDB

from typing import Type

from sdcm.sct_events import Severity
from sdcm.sct_events.base import SctEvent, SctEventProtocol


class PrometheusAlertManagerEvent(SctEvent, abstract=True):  # pylint: disable=too-many-instance-attributes
    _eq_attrs = (
        "type",
        "starts_at",
        "ends_at",
        "updated_at",
        "fingerprint",
        "labels",
        "description",
        "state",
        "alert_name",
    )

    start: Type[SctEventProtocol]
    end: Type[SctEventProtocol]

    def __init__(self, raw_alert: dict, severity: Severity = Severity.WARNING):
        super().__init__(severity=severity)

        self.annotations = raw_alert.get("annotations") or {}
        self.starts_at = raw_alert.get("startsAt")
        self.ends_at = raw_alert.get("endsAt")
        self.updated_at = raw_alert.get("updatedAt")
        self.fingerprint = raw_alert.get("fingerprint")
        self.status = raw_alert.get("status") or {}
        self.labels = raw_alert.get("labels") or {}

        self.description = self.annotations.get("description", self.annotations.get("summary", ""))
        self.state = self.status.get("state", "")
        self.alert_name = self.labels.get("alertname", "")

        try:
            self.severity = Severity[self.labels["sct_severity"]]
        except KeyError:
            pass

    @property
    def msgfmt(self) -> str:
        return super().msgfmt + ": " + "alert_name={0.alert_name} type={0.type} start={0.starts_at} " \
                                       "end={0.ends_at} description={0.description} updated={0.updated_at} " \
                                       "state={0.state} fingerprint={0.fingerprint} labels={0.labels}"

    def __eq__(self, other):
        return all(getattr(self, name, None) == getattr(other, name, None) for name in self._eq_attrs)


PrometheusAlertManagerEvent.add_subevent_type("start")
PrometheusAlertManagerEvent.add_subevent_type("end")
