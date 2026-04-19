import { useEffect, useState } from "react";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { useLoaderData, useFetcher } from "react-router";
import { authenticate } from "../shopify.server";
import { Page, Layout, Card, BlockStack, Text, TextField, Button, Box, InlineStack, Badge, Banner } from "@shopify/polaris";

const BACKEND_URL = "http://localhost:8000";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  
  try {
    const response = await fetch(`${BACKEND_URL}/api/dashboard/settings`);
    if (!response.ok) throw new Error("Backend offline");
    const settings = await response.json();
    return { settings };
  } catch (err) {
    console.error("Settings loader error:", err);
    return { 
        settings: { voice_id: "", base_personality: "" }, 
        error: "Could not connect to AI Voice Backend." 
    };
  }
};

export const action = async ({ request }: ActionFunctionArgs) => {
  await authenticate.admin(request);
  const formData = await request.formData();
  const voice_id = formData.get("voice_id") as string;
  const base_personality = formData.get("base_personality") as string;

  try {
    const response = await fetch(`${BACKEND_URL}/api/dashboard/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice_id, base_personality }),
    });
    if (!response.ok) throw new Error("Could not update");
    return { success: true };
  } catch (err) {
    return { error: "Failed to update agent settings." };
  }
};

export default function Settings() {
  const { settings, error } = useLoaderData<typeof loader>();
  const fetcher = useFetcher<typeof action>();
  
  const [voiceId, setVoiceId] = useState(settings.voice_id || "21m00Tcm4TlvDq8ikWAM"); // Default Rachel
  const [personality, setPersonality] = useState(settings.base_personality || "");

  const handleSave = () => {
    fetcher.submit({ voice_id: voiceId, base_personality: personality }, { method: "POST" });
  };

  const isSaving = fetcher.state === "submitting";

  return (
    <Page title="Agent Settings" backAction={{content: 'Dashboard', url: '/app'}}>
      <Layout>
        {error && (
            <Layout.Section>
                <Banner tone="critical">
                    <p>{error}</p>
                </Banner>
            </Layout.Section>
        )}

        <Layout.Section>
          <Card>
            <BlockStack gap="400">
              <Text variant="headingMd" as="h2">Global Personality</Text>
              <Text variant="bodyMd" as="p" tone="subdued">
                Define the default tone and behavior for your AI Voice Agent across all calls.
              </Text>
              <TextField
                label="System Prompt / Persona"
                value={personality}
                onChange={setPersonality}
                multiline={6}
                autoComplete="off"
                placeholder="e.g., You are a friendly, efficient support agent for Editorsbay. You help customers with order queries and aim for a positive resolution."
              />
            </BlockStack>
          </Card>
        </Layout.Section>

        <Layout.Section variant="oneThird">
          <Card>
            <BlockStack gap="400">
              <Text variant="headingMd" as="h2">Voice Identity</Text>
              <TextField
                label="ElevenLabs Voice ID"
                value={voiceId}
                onChange={setVoiceId}
                autoComplete="off"
                placeholder="Enter Voice ID"
                helpText="ID from your ElevenLabs Voice Lab."
              />
              <Box paddingBlockStart="400">
                 <Button 
                    variant="primary" 
                    onClick={handleSave}
                    loading={isSaving}
                 >
                    Save Settings
                 </Button>
              </Box>
            </BlockStack>
          </Card>
        </Layout.Section>

        <Layout.Section>
           <Card>
             <BlockStack gap="200">
               <Text variant="headingMd" as="h2">Advanced Rules</Text>
               <Text variant="bodyMd" as="p" tone="subdued">
                 Configure how the agent handles specific situations.
               </Text>
               <InlineStack align="space-between">
                  <Text variant="bodyMd" as="p">Human Handoff</Text>
                  <Badge tone="info">Email Notification</Badge>
               </InlineStack>
               <InlineStack align="space-between">
                  <Text variant="bodyMd" as="p">Transcription Language</Text>
                  <Text variant="bodyMd" as="p" fontWeight="bold">English (Auto-detect)</Text>
               </InlineStack>
             </BlockStack>
           </Card>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
