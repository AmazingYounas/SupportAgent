from app.services.shopify_service import ShopifyService


def test_shopify_service_uses_admin_access_token(monkeypatch):
    monkeypatch.setattr("app.services.shopify_service.settings.SHOPIFY_ADMIN_ACCESS_TOKEN", "token-123")
    monkeypatch.setattr("app.services.shopify_service.settings.SHOPIFY_SHOP_URL", "example.myshopify.com")
    service = ShopifyService()
    assert service.headers["X-Shopify-Access-Token"] == "token-123"
