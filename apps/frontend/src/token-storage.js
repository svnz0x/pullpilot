export const TOKEN_STORAGE_KEY = "pullpilot.bearerToken";

const STORAGE_PROVIDERS = [
  {
    id: "localStorage",
    label: "almacenamiento local",
    persistent: true,
  },
  {
    id: "sessionStorage",
    label: "almacenamiento de sesión",
    persistent: false,
  },
];

const describeProvider = (provider) => ({
  storage: provider.id,
  storageLabel: provider.label,
  persisted: provider.persistent,
});

const performStorageAction = (targetWindow, provider, action, { actionType } = {}) => {
  try {
    const storage = targetWindow?.[provider.id];
    const method = actionType || "setItem";
    if (!storage || typeof storage[method] !== "function") {
      throw new Error(`Storage ${provider.id} no disponible`);
    }
    const value = action(storage);
    return {
      ok: true,
      ...describeProvider(provider),
      action: actionType || null,
      value: value ?? null,
    };
  } catch (error) {
    return {
      ok: false,
      ...describeProvider(provider),
      action: actionType || null,
      error,
    };
  }
};

const collectErrors = (attempts) => attempts.filter((attempt) => attempt && attempt.ok === false);

const hadOnlyFailures = (attempts) => attempts.length > 0 && attempts.every((attempt) => attempt.ok === false);

export const createTokenStorage = (targetWindow = globalThis?.window) => {
  const safeWindow = targetWindow ?? {};

  const readToken = () => {
    const attempts = STORAGE_PROVIDERS.map((provider) =>
      performStorageAction(
        safeWindow,
        provider,
        (storage) => storage.getItem(TOKEN_STORAGE_KEY),
        { actionType: "getItem" },
      ),
    );

    let selected = null;
    for (const attempt of attempts) {
      if (attempt.ok) {
        const candidate = typeof attempt.value === "string" ? attempt.value : null;
        attempt.value = candidate;
        if (!selected && candidate) {
          selected = { ...attempt, value: candidate };
        }
      } else {
        attempt.value = null;
      }
    }

    const errors = collectErrors(attempts);
    const allFailed = hadOnlyFailures(attempts);

    return {
      ok: !allFailed,
      operation: "read",
      token: selected?.value ?? null,
      storage: selected?.storage ?? null,
      storageLabel: selected?.storageLabel ?? null,
      persisted: selected?.persisted ?? false,
      fallbackUsed: Boolean(selected && selected.storage !== STORAGE_PROVIDERS[0].id),
      attempts,
      errors,
      hadErrors: errors.length > 0,
    };
  };

  const clearToken = (operation = "clear") => {
    const attempts = STORAGE_PROVIDERS.map((provider) =>
      performStorageAction(
        safeWindow,
        provider,
        (storage) => {
          storage.removeItem(TOKEN_STORAGE_KEY);
          return null;
        },
        { actionType: "removeItem" },
      ),
    );

    const errors = collectErrors(attempts);

    return {
      ok: errors.length === 0,
      operation,
      storage: null,
      storageLabel: null,
      persisted: false,
      fallbackUsed: false,
      attempts,
      errors,
      hadErrors: errors.length > 0,
    };
  };

  const persistToken = (token) => {
    const attempts = [];
    const [primary, ...fallbacks] = STORAGE_PROVIDERS;

    const primaryAttempt = performStorageAction(
      safeWindow,
      primary,
      (storage) => {
        storage.setItem(TOKEN_STORAGE_KEY, token);
        return token;
      },
      { actionType: "setItem" },
    );
    attempts.push(primaryAttempt);

    if (primaryAttempt.ok) {
      for (const fallbackProvider of fallbacks) {
        const removalAttempt = performStorageAction(
          safeWindow,
          fallbackProvider,
          (storage) => {
            storage.removeItem(TOKEN_STORAGE_KEY);
            return null;
          },
          { actionType: "removeItem" },
        );
        attempts.push(removalAttempt);
      }

      const errors = collectErrors(attempts);
      return {
        ok: errors.length === 0,
        operation: "write",
        storage: primaryAttempt.storage,
        storageLabel: primaryAttempt.storageLabel,
        persisted: primaryAttempt.persisted,
        fallbackUsed: false,
        attempts,
        errors,
        hadErrors: errors.length > 0,
      };
    }

    let fallbackResult = null;
    for (const fallbackProvider of fallbacks) {
      const fallbackAttempt = performStorageAction(
        safeWindow,
        fallbackProvider,
        (storage) => {
          storage.setItem(TOKEN_STORAGE_KEY, token);
          return token;
        },
        { actionType: "setItem" },
      );
      fallbackAttempt.fallback = true;
      attempts.push(fallbackAttempt);
      if (!fallbackResult && fallbackAttempt.ok) {
        fallbackResult = fallbackAttempt;
      }
    }

    const errors = collectErrors(attempts);

    if (fallbackResult) {
      return {
        ok: true,
        operation: "write",
        storage: fallbackResult.storage,
        storageLabel: fallbackResult.storageLabel,
        persisted: fallbackResult.persisted,
        fallbackUsed: true,
        attempts,
        errors,
        hadErrors: errors.length > 0,
      };
    }

    return {
      ok: false,
      operation: "write",
      storage: null,
      storageLabel: null,
      persisted: false,
      fallbackUsed: false,
      attempts,
      errors,
      hadErrors: errors.length > 0,
    };
  };

  return {
    readToken,
    clearToken,
    persistToken,
  };
};

export default createTokenStorage;
