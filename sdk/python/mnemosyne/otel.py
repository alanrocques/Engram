"""
OpenTelemetry exporter for automatic trace ingestion.

This module provides an OTel SpanExporter that automatically sends
traces to the Mnemosyne service.

TODO: Implement in Phase 4
"""


class MnemosyneSpanExporter:
    """OpenTelemetry SpanExporter for Mnemosyne."""

    def __init__(self, client):
        self.client = client

    # TODO: Implement OTel span export
