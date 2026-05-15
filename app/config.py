from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    kitchen_token: str = "dev-token"
    resend_api_key: str = ""
    restaurant_email: str = ""
    from_email: str = "orders@example.com"
    printer_ip: str = "192.168.1.100"
    printer_port: int = 9100
    printer_enabled: bool = False
    database_url: str = "sqlite:///./orders.db"

    # Restaurant info
    restaurant_name: str = "Happy Gate"
    restaurant_phone: str = "+31 346 213 777"
    restaurant_address: str = "Dorpsweg 154, 3738CK Maartensdijk, Netherlands"
    restaurant_currency: str = "EUR"
    restaurant_cuisine: str = "Chinese"
    restaurant_language: str = "nl"

    # Service configuration
    service_pickup: bool = True
    service_delivery: bool = False
    service_dine_in: bool = True
    anonymous_ordering: bool = True

    # Scheduling
    opening_time: str = "16:00"
    closing_time: str = "20:00"
    scheduling_interval_minutes: int = 15

    class Config:
        env_file = ".env"


settings = Settings()
