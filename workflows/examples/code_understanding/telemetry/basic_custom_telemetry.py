from .custom_telemetry import CustomTelemetry


class BasicCustomTelemetry(CustomTelemetry):
    """No-op telemetry provider."""

    def track(self):
        import litellm
        from .telemetry_litellm.basic_token_logger import BasicTokenLogger

        litellm.callbacks = [BasicTokenLogger()]

    @staticmethod
    def get_token_usage(kfp_run_id: str) -> dict:
        return {}
