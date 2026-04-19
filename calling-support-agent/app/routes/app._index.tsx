import { useEffect, useState } from "react";
import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { Page, Layout, Card, Grid, Text, BlockStack, InlineStack, Badge, Box } from "@shopify/polaris";
import { PhoneIcon, IncomingIcon, OutgoingIcon, ChartBarIcon } from "@shopify/polaris-icons";

const BACKEND_URL = "http://localhost:8000";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  
  try {
    const response = await fetch(`${BACKEND_URL}/api/dashboard/stats`);
    if (!response.ok) throw new Error("Backend offline");
    const stats = await response.json();
    return { stats };
  } catch (err) {
    console.error("Dashboard loader error:", err);
    return { 
      stats: {
        total_calls: 0,
        inbound_count: 0,
        outbound_count: 0,
        active_count: 0,
        resolution_rate: 0
      },
      error: "Could not connect to AI Voice Backend. Ensure the Python server is running."
    };
  }
};

export default function Index() {
  const { stats: initialStats, error } = useLoaderData<typeof loader>();
  const [stats, setStats] = useState(initialStats);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    
    // Auto-refresh stats every 4 seconds to track live calls
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/dashboard/stats`);
        if (response.ok) {
          const newStats = await response.json();
          setStats(newStats);
        }
      } catch (e) {
        console.error("Auto-refresh failed", e);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, []);

  return (
    <Page title="Voice Command Center" fullWidth>
      {error && (
        <Box paddingBlockEnd="400">
           <Badge tone="critical">{error}</Badge>
        </Box>
      )}

      <Layout>
        {/* KPI Section */}
        <Layout.Section>
          <Grid>
            <Grid.Cell columnSpan={{ xs: 6, sm: 3, md: 3, lg: 3 }}>
              <StatCard 
                title="Total Calls" 
                value={stats.total_calls} 
                icon={PhoneIcon} 
                color="#f0f7ff" 
                delay="0s" 
                mounted={mounted}
              />
            </Grid.Cell>
            <Grid.Cell columnSpan={{ xs: 6, sm: 3, md: 3, lg: 3 }}>
              <StatCard 
                title="Active Now" 
                value={stats.active_count} 
                icon={PhoneIcon} 
                color="#fff0f0" 
                badge={stats.active_count > 0 ? "LIVE" : null}
                delay="0.1s"
                mounted={mounted}
              />
            </Grid.Cell>
            <Grid.Cell columnSpan={{ xs: 6, sm: 3, md: 3, lg: 3 }}>
              <StatCard 
                title="Inbound" 
                value={stats.inbound_count} 
                icon={IncomingIcon} 
                color="#f0fff4" 
                delay="0.2s"
                mounted={mounted}
              />
            </Grid.Cell>
            <Grid.Cell columnSpan={{ xs: 6, sm: 3, md: 3, lg: 3 }}>
              <StatCard 
                title="Outbound" 
                value={stats.outbound_count} 
                icon={OutgoingIcon} 
                color="#fdfcf0" 
                delay="0.3s"
                mounted={mounted}
              />
            </Grid.Cell>
          </Grid>
        </Layout.Section>

        {/* Analytics & Pulse */}
        <Layout.Section variant="oneThird">
          <Card>
            <BlockStack gap="400">
              <Text variant="headingMd" as="h2">Resolution Rate</Text>
              <Box padding="600" background="bg-surface-secondary" borderRadius="200">
                <BlockStack align="center" gap="200">
                  <Text variant="heading3xl" as="p" alignment="center">
                    {stats.resolution_rate}%
                  </Text>
                  <Text variant="bodySm" as="p" tone="subdued" alignment="center">
                    of queries resolved by AI
                  </Text>
                </BlockStack>
              </Box>
              <Text variant="bodySm" as="p" tone="subdued">
                Calculated from all completed inbound sessions.
              </Text>
            </BlockStack>
          </Card>
        </Layout.Section>

        <Layout.Section>
          <Card>
            <BlockStack gap="400">
              <InlineStack align="space-between">
                <Text variant="headingMd" as="h2">Platform Health</Text>
                <Badge tone="success">Operational</Badge>
              </InlineStack>
              <Box padding="400" background="bg-surface-secondary" borderRadius="200">
                 <BlockStack gap="200">
                    <InlineStack align="space-between">
                       <Text variant="bodyMd" as="p">STT Latency</Text>
                       <Text variant="bodyMd" as="p" fontWeight="bold">~240ms</Text>
                    </InlineStack>
                    <InlineStack align="space-between">
                       <Text variant="bodyMd" as="p">TTS Buffer</Text>
                       <Text variant="bodyMd" as="p" fontWeight="bold">0.8s</Text>
                    </InlineStack>
                 </BlockStack>
              </Box>
            </BlockStack>
          </Card>
        </Layout.Section>
      </Layout>

      <style>{`
        @keyframes fadeInSlideUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .stat-card-animated {
          opacity: 0;
          animation: fadeInSlideUp 0.6s ease forwards;
        }
      `}</style>
    </Page>
  );
}

function StatCard({ title, value, icon: Icon, color, badge, delay, mounted }: any) {
  return (
    <div className={mounted ? "stat-card-animated" : ""} style={{ animationDelay: delay }}>
      <Card>
        <BlockStack gap="200">
          <InlineStack align="space-between">
            <Box padding="200" background="bg-surface-secondary" borderRadius="200" style={{ backgroundColor: color }}>
              <Icon width="20" />
            </Box>
            {badge && <Badge tone="attention">{badge}</Badge>}
          </InlineStack>
          <Text variant="bodySm" as="p" tone="subdued">{title}</Text>
          <Text variant="headingLg" as="p">{value}</Text>
        </BlockStack>
      </Card>
    </div>
  );
}
