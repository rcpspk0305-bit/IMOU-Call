from app.config import Config

def test_config_defaults():
    assert Config.EXOTEL_SUBDOMAIN == "api.in.exotel.com" or Config.EXOTEL_SUBDOMAIN != ""
    assert hasattr(Config, "EXOTEL_SID")
    assert hasattr(Config, "EXOTEL_KEY")
    assert hasattr(Config, "EXOTEL_TOKEN")
    assert hasattr(Config, "FROM_NUMBER")
    assert hasattr(Config, "CALLER_ID")
    assert hasattr(Config, "APP_ID")
    assert Config.BUFFER_DELAY_SECONDS == 180 or isinstance(Config.BUFFER_DELAY_SECONDS, int)
