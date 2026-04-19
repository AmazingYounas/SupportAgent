import { useEffect, useState } from "react";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { useLoaderData, useFetcher } from "react-router";
import { authenticate } from "../shopify.server";
import { Page, Layout, Card, ResourceList, ResourceItem, Text, Badge, Button, BlockStack, InlineStack, Box, Modal, TextField, Select } from "@shopify/polaris";
import { PlusIcon } from "@shopify/polaris-icons";

const BACKEND_URL = "http://localhost:8000";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  
  try {
    const response = await fetch(`${BACKEND_URL}/api/dashboard/campaigns`);
    if (!response.ok) throw new Error("Backend offline");
    const campaigns = await response.json();
    return { campaigns };
  } catch (err) {
    console.error("Automations loader error:", err);
    return { campaigns: [], error: "Could not fetch automations." };
  }
};

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.admin(request);
  const formData = await request.formData();
  const name = formData.get("name") as string;
  const trigger_event = formData.get("trigger_event") as string;
  const goal_prompt = formData.get("goal_prompt") as string;

  try {
    const response = await fetch(`${BACKEND_URL}/api/dashboard/campaigns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, trigger_event, active: 1, goal_prompt }),
    });
    if (!response.ok) throw new Error("Could not create");
    return { success: true };
  } catch (err) {
    return { error: "Failed to create automation rule." };
  }
};

export default function Automations() {
  const { campaigns, error } = useLoaderData<typeof loader>();
  const fetcher = useFetcher<typeof action>();
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("orders/create");
  const [goal, setGoal] = useState("");

  const handleCreate = () => {
    fetcher.submit({ name, trigger_event: trigger, goal_prompt: goal }, { method: "POST" });
    setIsModalOpen(false);
  };

  return (
    <Page 
        title="Call Automations" 
        backAction={{content: 'Dashboard', url: '/app'}}
        primaryAction={{
            content: 'Create Automation',
            icon: PlusIcon,
            onClick: () => setIsModalOpen(true)
        }}
    >
      <Layout>
        <Layout.Section>
          <Card padding="0">
            <ResourceList
              resourceName={{singular: 'automation', plural: 'automations'}}
              items={campaigns}
              renderItem={(item: any) => {
                const {id, name, trigger_event, active, goal_prompt} = item;
                return (
                  <ResourceItem
                    id={id}
                    onClick={() => {}}
                    accessibilityLabel={`View details for ${name}`}
                  >
                    <InlineStack align="space-between">
                        <BlockStack gap="100">
                            <Text variant="bodyMd" fontWeight="bold" as="h3">{name}</Text>
                            <Text variant="bodySm" tone="subdued" as="p">Trigger: <b>{trigger_event}</b></Text>
                        </BlockStack>
                        <InlineStack gap="200">
                           {active ? <Badge tone="success">Active</Badge> : <Badge tone="subdued">Inactive</Badge>}
                           <Button variant="tertiary">Edit</Button>
                        </InlineStack>
                    </InlineStack>
                    <Box paddingBlockStart="200">
                        <Text variant="bodySm" tone="subdued" as="p">{goal_prompt || "General AI Support personality."}</Text>
                    </Box>
                  </ResourceItem>
                );
              }}
            />
            {campaigns.length === 0 && (
                <Box padding="800">
                    <BlockStack align="center" gap="400">
                         <Text variant="bodyMd" as="p" alignment="center">No automation rules configured yet.</Text>
                         <Button onClick={() => setIsModalOpen(true)}>Set up your first rule</Button>
                    </BlockStack>
                </Box>
            )}
          </Card>
        </Layout.Section>
      </Layout>

      <Modal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Create Outbound Automation"
        primaryAction={{
          content: 'Save Automation',
          onClick: handleCreate,
          loading: fetcher.state === "submitting"
        }}
        secondaryActions={[
          {
            content: 'Cancel',
            onClick: () => setIsModalOpen(false),
          },
        ]}
      >
        <Modal.Section>
          <BlockStack gap="400">
            <TextField
              label="Automation Name"
              value={name}
              onChange={setName}
              autoComplete="off"
              placeholder="e.g., New Order Confirmation"
            />
            <Select
              label="Shopify Trigger Event"
              options={[
                {label: 'New Order Created', value: 'orders/create'},
                {label: 'Order Cancelled', value: 'orders/cancelled'},
                {label: 'Abandoned Checkout', value: 'checkouts/create'},
              ]}
              onChange={setTrigger}
              value={trigger}
            />
            <TextField
              label="Call Goal (Instructions for AI)"
              value={goal}
              onChange={setGoal}
              multiline={4}
              autoComplete="off"
              placeholder="Tell the AI what to accomplish in this call..."
              helpText="e.g., 'Greet the user, confirm their address, and ask if they need anything else.'"
            />
          </BlockStack>
        </Modal.Section>
      </Modal>
    </Page>
  );
}
