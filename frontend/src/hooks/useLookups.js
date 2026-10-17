import { useMemo } from "react";
import { getProjects } from "../features/projects/services/projectService.js";
import { getWorkers } from "../features/workforce/services/workforceService.js";
import { getId, missingRecord, normalizeList, projectName, workerName } from "../lib/utils.js";
import { useAsyncData } from "./useAsyncData.js";

// Real project records for dropdowns and id -> name display.
export function useProjectOptions({ enabled = true } = {}) {
  const query = useAsyncData(async () => normalizeList(await getProjects()).items, [], { initialData: [], enabled });
  const byId = useMemo(() => new Map((query.data || []).map((project) => [getId(project), project])), [query.data]);
  return {
    projects: query.data || [],
    loading: query.loading,
    error: query.error,
    reload: query.reload,
    nameOf: (id) => (id ? (byId.has(id) ? projectName(byId.get(id)) : missingRecord("Project", query)) : "Not set"),
  };
}

// Real worker records for dropdowns and id -> name display.
export function useWorkerOptions({ enabled = true } = {}) {
  const query = useAsyncData(async () => normalizeList(await getWorkers()).items, [], { initialData: [], enabled });
  const byId = useMemo(() => new Map((query.data || []).map((worker) => [getId(worker), worker])), [query.data]);
  return {
    workers: query.data || [],
    loading: query.loading,
    error: query.error,
    reload: query.reload,
    nameOf: (id) => (id ? (byId.has(id) ? workerName(byId.get(id)) : missingRecord("Worker", query)) : "Not set"),
  };
}
