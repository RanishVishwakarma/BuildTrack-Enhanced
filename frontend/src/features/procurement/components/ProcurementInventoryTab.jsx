import { useState } from "react";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Modal } from "../../../components/ui/Modal.jsx";
import { formatDateTime, formatNumber, formatStatus, getId } from "../../../lib/utils.js";
import { useProcurementList } from "../hooks/useProcurementList.js";
import { getProcurementInventory } from "../services/procurementService.js";
import { ListSection } from "./ListSection.jsx";

// Read-only stock view built by the backend from both inventory records and
// procurement deliveries (GET /procurement/inventory). Stock changes happen
// through deliveries here, or through stock movements on the Inventory page.
export function ProcurementInventoryTab() {
  const list = useProcurementList(getProcurementInventory);
  const [history, setHistory] = useState(null);

  const columns = [
    { key: "material", header: "Material", render: (row) => <span className="font-semibold">{row.material}</span> },
    { key: "stock_quantity", header: "Stock", render: (row) => `${formatNumber(row.stock_quantity)} ${row.unit || ""}` },
    { key: "updated_at", header: "Last updated", render: (row) => formatDateTime(row.updated_at) },
    { key: "transactions", header: "Movements", render: (row) => (row.transactions || []).length },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <Button disabled={!(row.transactions || []).length} onClick={() => setHistory(row)} size="sm" variant="secondary">History</Button>
      ),
    },
  ];

  return (
    <>
      <ListSection
        columns={columns}
        emptyDescription="Stock appears once inventory items exist or deliveries are received."
        emptyTitle="No stock records"
        exportName="inventory"
        getRowId={(row) => getId(row) || row.material}
        list={list}
        searchPlaceholder="Search material..."
        title="Procurement inventory"
      />
      <Modal onClose={() => setHistory(null)} open={Boolean(history)} size="lg" title={`Stock history · ${history?.material || ""}`}>
        {history ? (
          <DataTable
            columns={[
              { key: "type", header: "Type", render: (row) => formatStatus(row.transaction_type) },
              { key: "quantity", header: "Change", render: (row) => `${Number(row.delta ?? row.quantity) > 0 ? "+" : ""}${formatNumber(row.delta ?? row.quantity)} ${row.unit || ""}` },
              { key: "created_by", header: "By" },
              { key: "remarks", header: "Remarks", render: (row) => row.remarks || row.reason || "Not set" },
              { key: "created_at", header: "Date", render: (row) => formatDateTime(row.created_at) },
            ]}
            rows={history.transactions || []}
          />
        ) : null}
      </Modal>
    </>
  );
}
