import test from "node:test";
import assert from "node:assert/strict";

import { createTokenStorage, TOKEN_STORAGE_KEY } from "../src/token-storage.js";

class MemoryStorage {
  constructor() {
    this.store = new Map();
    this.throwOnGet = null;
    this.throwOnSet = null;
    this.throwOnRemove = null;
  }

  setItem(key, value) {
    if (this.throwOnSet) {
      throw this.throwOnSet;
    }
    this.store.set(key, String(value));
  }

  getItem(key) {
    if (this.throwOnGet) {
      throw this.throwOnGet;
    }
    return this.store.has(key) ? this.store.get(key) : null;
  }

  removeItem(key) {
    if (this.throwOnRemove) {
      throw this.throwOnRemove;
    }
    this.store.delete(key);
  }

  clear() {
    this.store.clear();
  }
}

const createQuotaExceededError = () => {
  const error = new Error("QuotaExceededError");
  error.name = "QuotaExceededError";
  return error;
};

test("fallback sessionStorage keeps the token when localStorage quota is exceeded", () => {
  const localStorage = new MemoryStorage();
  const sessionStorage = new MemoryStorage();
  const quotaError = createQuotaExceededError();

  localStorage.throwOnSet = quotaError;
  localStorage.throwOnGet = quotaError;
  localStorage.throwOnRemove = quotaError;

  const windowMock = {
    localStorage,
    sessionStorage,
  };

  const storage = createTokenStorage(windowMock);
  const token = "secret-token";

  const writeStatus = storage.persistToken(token);
  assert.ok(writeStatus.ok, "the storage operation should succeed using a fallback");
  assert.equal(writeStatus.fallbackUsed, true, "the fallback storage should be used");
  assert.equal(writeStatus.storage, "sessionStorage", "the fallback storage should be sessionStorage");
  assert.equal(
    sessionStorage.getItem(TOKEN_STORAGE_KEY),
    token,
    "the token should be kept in sessionStorage",
  );

  const readStatus = storage.readToken();
  assert.ok(readStatus.ok, "reading should succeed thanks to the fallback storage");
  assert.equal(readStatus.fallbackUsed, true, "the fallback should be detected when reading");
  assert.equal(readStatus.token, token, "the fallback token should be returned");
  assert.equal(
    readStatus.errors?.[0]?.storage,
    "localStorage",
    "the read status should record the localStorage failure",
  );
});
