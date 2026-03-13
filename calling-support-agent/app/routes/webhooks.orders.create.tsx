import type { ActionFunctionArgs } from "react-router";
import { authenticate } from "../shopify.server";

export const action = async ({ request }: ActionFunctionArgs) => {
  const { shop, topic, payload } = await authenticate.webhook(request);

  if (topic === "ORDERS_CREATE") {
    console.log(`\n--- Order Webhook Caught ---`);
    console.log(`Shop: ${shop}`);
    console.log(`Order ID: ${payload.id}`);
    console.log(`Customer Phone: ${payload.phone || payload.customer?.phone || "N/A"}`);
    
    // TODO: Phase 2 - Forward this payload to the Python AI server via HTTP POST.
    console.log(`----------------------------\n`);
  }

  return new Response();
};
