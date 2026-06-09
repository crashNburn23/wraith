import axios from "axios";
import { clearToken, getToken } from "./auth";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !err.config.url.endsWith("/auth/login")) {
      clearToken();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export default api;

export const auth = {
  login: (username, password) =>
    api.post("/auth/login", { username, password }).then((r) => r.data),
};

export const sources = {
  list: () => api.get("/sources").then(r => r.data),
  create: (body) => api.post("/sources", body).then(r => r.data),
  update: (id, body) => api.patch(`/sources/${id}`, body).then(r => r.data),
  delete: (id) => api.delete(`/sources/${id}`),
  importCsv: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/sources/import-csv", fd, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data);
  },
};

export const ingest = {
  run: () => api.post("/ingest/run").then(r => r.data),
  status: () => api.get("/ingest/status").then(r => r.data),
};

export const enrich = {
  run: () => api.post("/enrich/run").then(r => r.data),
  status: () => api.get("/enrich/status").then(r => r.data),
  pause: () => api.post("/enrich/pause").then(r => r.data),
  resume: () => api.post("/enrich/resume").then(r => r.data),
  prompt: () => api.get("/enrich/prompt").then(r => r.data),
  runSingle: (id) => api.post(`/enrich/articles/${id}`).then(r => r.data),
  patchEntity: (type, id, body) => api.patch(`/enrich/entities/${type}/${id}`, body).then(r => r.data),
};

export const articles = {
  list: (params) => api.get("/articles", { params }).then(r => r.data),
  get: (id) => api.get(`/articles/${id}`).then(r => r.data),
};

export const bulletin = {
  today: () => api.get("/bulletin/today").then(r => r.data),
  history: () => api.get("/bulletin/history").then(r => r.data),
  get: (date) => api.get(`/bulletin/${date}`).then(r => r.data),
  build: () => api.post("/bulletin/build").then(r => r.data),
  generateBrief: () => api.post("/bulletin/brief/generate").then(r => r.data),
  scoreBreakdown: (itemId) => api.get(`/bulletin/items/${itemId}/score-breakdown`).then(r => r.data),
  rebuildItemScore: (itemId) => api.post(`/bulletin/rebuild-item/${itemId}`).then(r => r.data),
};

export const feedback = {
  rate: (articleId, rating) => api.post("/feedback", { article_id: articleId, rating }).then(r => r.data),
  getForArticle: (id) => api.get(`/feedback/article/${id}`).then(r => r.data),
  setReasons: (articleId, reasonTags) => api.patch(`/feedback/${articleId}/reasons`, { reason_tags: reasonTags }).then(r => r.data),
  setReadStatus: (articleId, status) => api.patch(`/feedback/read-status/${articleId}`, { status }).then(r => r.data),
  getReadStatus: (articleId) => api.get(`/feedback/read-status/${articleId}`).then(r => r.data),
  summarize: () => api.post("/feedback/summarize").then(r => r.data),
  applyNote: (text) => api.post("/feedback/notes/apply", { text }).then(r => r.data),
};

export const search = {
  articles: (params) => api.get("/search", { params }).then(r => r.data),
  ioc: (q, ioc_type) => api.get("/search/ioc", { params: { q, ioc_type } }).then(r => r.data),
  actors: (q = "") => api.get("/search/actors", { params: { q } }).then(r => r.data),
  actor: (id) => api.get(`/search/actors/${id}`).then(r => r.data),
  tags: () => api.get("/search/tags").then(r => r.data),
};

export const cve = {
  list: (params) => api.get("/cve", { params }).then(r => r.data),
  stats: () => api.get("/cve/stats").then(r => r.data),
  get: (id) => api.get(`/cve/${id}`).then(r => r.data),
  sync: () => api.post("/cve/sync").then(r => r.data),
};

export const settings = {
  getScoring: () => api.get("/settings/scoring").then(r => r.data),
  updateScoring: (body) => api.patch("/settings/scoring", body).then(r => r.data),
  resetScoring: () => api.post("/settings/scoring/reset").then(r => r.data),
  feedbackSignal: () => api.get("/settings/feedback-signal").then(r => r.data),
  scheduler: () => api.get("/settings/scheduler").then(r => r.data),
  prune: () => api.post("/settings/prune").then(r => r.data),
  getProfile: () => api.get("/settings/profile").then(r => r.data),
  updateProfile: (body) => api.patch("/settings/profile", body).then(r => r.data),
};

export const chat = {
  health: () => api.get("/chat/health").then(r => r.data),
};

export const entities = {
  cve:   (cveId)   => api.get(`/entities/cve/${cveId}`).then(r => r.data),
  ioc:   (iocId)   => api.get(`/entities/ioc/${iocId}`).then(r => r.data),
  actor: (actorId) => api.get(`/entities/actor/${actorId}`).then(r => r.data),
};
