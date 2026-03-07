"""
OpenTelemetry exporter for automatic trace ingestion.

This module provides an OTel SpanExporter that automatically sends
traces to the Engram service.

TODO: Implement in Phase 4
"""


class EngramSpanExporter:
    """OpenTelemetry SpanExporter for Engram."""

    def __init__(self, client):
        self.client = client

    # TODO: Implement OTel span export
