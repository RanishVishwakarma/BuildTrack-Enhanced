import { Download, Plus } from "lucide-react";
import toast from "react-hot-toast";
import { ErrorState } from "../../../components/common/ErrorState.jsx";
import { LoadingState } from "../../../components/common/LoadingState.jsx";
import { Pagination } from "../../../components/common/Pagination.jsx";
import { SearchInput } from "../../../components/common/SearchInput.jsx";
import { DataTable } from "../../../components/data-display/DataTable.jsx";
import { Button } from "../../../components/ui/Button.jsx";
import { Select } from "../../../components/ui/Select.jsx";
import { formatStatus } from "../../../lib/utils.js";
import { usePageRefresh } from "../../../layouts/pageMeta.js";
import { getApiErrorMessage } from "../../../services/apiError.js";
import { downloadBlob } from "../../../services/fileDownload.js";
import { exportCollection } from "../services/procurementService.js";
import { PAGE_SIZE } from "../hooks/useProcurementList.js";

export function ListSection({
  title,
  list,
  columns,
  searchPlaceholder = "Search...",
  statusOptions,
  priorityOptions,
  exportName,
  addLabel,
  onAdd,
  emptyTitle,
  emptyDescription,
  getRowId,
  hideFilters = false,
}) {
  // The navbar refresh button reloads this list.
  usePageRefresh(list.reload);
  async function exportCsv() {
    try {
      downloadBlob(await exportCollection(exportName), `${exportName}.csv`);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Export failed."));
    }
  }

  return (
    <section className="card">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        <div className="flex flex-wrap gap-2">
          {exportName ? <Button onClick={exportCsv} size="sm" variant="secondary"><Download className="h-4 w-4" /> Export CSV</Button> : null}
          {onAdd ? <Button onClick={onAdd} size="sm"><Plus className="h-4 w-4" /> {addLabel}</Button> : null}
        </div>
      </div>
      {!hideFilters ? (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2">
            <SearchInput aria-label={searchPlaceholder} placeholder={searchPlaceholder} value={list.filters.search} onChange={(event) => list.setSearch(event.target.value)} />
          </div>
          {statusOptions ? (
            <Select aria-label="Filter by status" className="h-10" value={list.filters.status} onChange={(event) => list.setStatus(event.target.value)}>
              <option value="">All statuses</option>
              {statusOptions.map((status) => <option key={status} value={status}>{formatStatus(status)}</option>)}
            </Select>
          ) : null}
          {priorityOptions ? (
            <Select aria-label="Filter by priority" className="h-10" value={list.filters.priority} onChange={(event) => list.setPriority(event.target.value)}>
              <option value="">All priorities</option>
              {priorityOptions.map((priority) => <option key={priority} value={priority}>{formatStatus(priority)}</option>)}
            </Select>
          ) : null}
        </div>
      ) : null}
      {list.loading ? <LoadingState label={`Loading ${title.toLowerCase()}...`} /> : null}
      {!list.loading && list.error ? <ErrorState message={getApiErrorMessage(list.error)} onRetry={list.reload} /> : null}
      {!list.loading && !list.error ? (
        <>
          <DataTable columns={columns} emptyDescription={emptyDescription} emptyTitle={emptyTitle} getRowId={getRowId} rows={list.items} />
          <Pagination onPageChange={list.setPage} page={list.filters.page} pageSize={PAGE_SIZE} total={list.total} />
        </>
      ) : null}
    </section>
  );
}

export function RowActions({ children }) {
  return <div className="flex flex-wrap gap-2">{children}</div>;
}
