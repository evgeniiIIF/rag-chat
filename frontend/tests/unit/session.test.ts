import { describe, expect, it, vi } from "vitest";
import { getSessionId, resetSessionId } from "@/features/chat/session";

describe("session id", () => {
  it("creates id, stores in localStorage, returns same id", () => {
    const id1 = getSessionId();
    expect(id1).toBeTypeOf("string");
    expect(id1.length).toBeGreaterThan(1);
    const id2 = getSessionId();
    expect(id2).toBe(id1);
  });

  it("falls back to memory when localStorage throws", () => {
    const spyGet = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("nope");
    });
    const spySet = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("nope");
    });
    try {
      const id1 = getSessionId();
      expect(id1).toBeTypeOf("string");
      expect(id1.length).toBeGreaterThan(1);
      const id2 = getSessionId();
      expect(id2).toBe(id1);
    } finally {
      spyGet.mockRestore();
      spySet.mockRestore();
    }
  });

  it("resetSessionId returns fresh id and stores it", () => {
    const before = getSessionId();
    const fresh = resetSessionId();
    expect(fresh).not.toBe(before);
    expect(getSessionId()).toBe(fresh);
  });
});