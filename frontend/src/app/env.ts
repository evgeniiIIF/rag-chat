import { z } from "zod";

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().min(1).default("/api"),
  VITE_APP_NAME: z.string().min(1).default("RAG Chat"),
});

const raw: unknown = import.meta.env;
const parsed = envSchema.parse(raw);

export interface AppEnv {
  apiBaseUrl: string;
  appName: string;
}

export const env: AppEnv = {
  apiBaseUrl: parsed.VITE_API_BASE_URL,
  appName: parsed.VITE_APP_NAME,
};
