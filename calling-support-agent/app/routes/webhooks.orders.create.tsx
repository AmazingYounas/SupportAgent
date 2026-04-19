import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";

const BACKEND_URL = "http://localhost:8000";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

  if (topic === "ORDERS_CREATE") {
    console.log(`[Webhook] Forwarding Order ${payload.id} to AI Voice Backend...`);
    
    try {
      // Forward the raw request to Python backend for HMAC verification
      // OR just send the payload if we trust the internal network
      // For now, let's send the payload.
      await fetch(`${BACKEND_URL}/api/webhooks/shopify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Shopify-Topic": "orders/create",
          "X-Shopify-Shop-Domain": shop,
        },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.error("[Webhook] Failed to forward to AI backend:", err);
    }
  }

  return new Response();
};
