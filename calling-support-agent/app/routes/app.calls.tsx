import { useEffect } from "react";
import type { LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { Page, Layout, Card, IndexTable, Text, Badge, BlockStack, InlineStack, useIndexResourceState } from "@shopify/polaris";
import { format } from "date-fns";

const BACKEND_URL = "http://localhost:8000";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  
  try {
    const response = await fetch(`${BACKEND_URL}/api/dashboard/history?limit=100`);
    if (!response.ok) throw new Error("Backend offline");
    const history = await response.json();
    return { history };
  } catch (err) {
    console.error("Calls loader error:", err);
    return { history: [], error: "Could not fetch call logs." };
  }
};

export default function Calls() {
  const { history: initialHistory, error } = useLoaderData<typeof loader>();
  const [history, setHistory] = useState(initialHistory);

  useEffect(() => {
    // Polling history every 5 seconds to show live session transitions
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/dashboard/history?limit=100`);
        if (response.ok) {
          const newHistory = await response.json();
          setHistory(newHistory);
        }
      } catch (e) {
        console.error("History polling failed", e);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const resourceName = {
    singular: 'call',
    plural: 'calls',
  };

  const {selectedResources, allResourcesSelected, handleSelectionChange} =
    useIndexResourceState(history);

  const rowMarkup = history.map(
    (
      {id, customer_name, session_key, direction, status, outcome, summary, duration_seconds, created_at}: any,
      index: number,
    ) => (
      <IndexTable.Row
        id={id}
        key={id}
        selected={selectedResources.includes(id)}
        position={index}
      >
        <IndexTable.Cell>
          <Text variant="bodyMd" fontWeight="bold" as="span">
            {format(new Date(created_at), 'MMM d, HH:mm')}
          </Text>
        </IndexTable.Cell>
        <IndexTable.Cell>{customer_name}</IndexTable.Cell>
        <IndexTable.Cell>
          <Badge tone={direction === 'INBOUND' ? 'info' : 'attention'}>
            {direction}
          </Badge>
        </IndexTable.Cell>
        <IndexTable.Cell>
          <Badge tone={status === 'COMPLETED' ? 'success' : 'attention'}>
            {status}
          </Badge>
        </IndexTable.Cell>
        <IndexTable.Cell>
          {outcome ? (
            <Badge tone="warning">{outcome}</Badge>
          ) : (
             <Text tone="subdued" as="span">-</Text>
          )}
        </IndexTable.Cell>
        <IndexTable.Cell>{duration_seconds}s</IndexTable.Cell>
        <IndexTable.Cell>
           <Text variant="bodySm" tone="subdued" as="span" breakWord>
             {summary || "No summary available."}
           </Text>
        </IndexTable.Cell>
        <IndexTable.Cell>
            {(direction === 'OUTBOUND' || status === 'ACTIVE') && session_key && (
               <Button url={`/app/simulator/${session_key}`}>Simulate</Button>
            )}
        </IndexTable.Cell>
      </IndexTable.Row>
    ),
  );

  return (
    <Page title="Call Logs" backAction={{content: 'Dashboard', url: '/app'}}>
      <Layout>
        <Layout.Section>
          <Card padding="0">
            <IndexTable
              resourceName={resourceName}
              itemCount={history.length}
              selectedItemsCount={
                allResourcesSelected ? 'All' : selectedResources.length
              }
              onSelectionChange={handleSelectionChange}
              headings={[
                {title: 'Date'},
                {title: 'Customer'},
                {title: 'Direction'},
                {title: 'Status'},
                {title: 'Outcome'},
                {title: 'Duration'},
                {title: 'AI Summary'},
                {title: 'Actions'},
              ]}
            >
              {rowMarkup}
            </IndexTable>
          </Card>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
