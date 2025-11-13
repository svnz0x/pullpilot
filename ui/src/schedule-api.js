export const createScheduleApi = ({ authorizedFetch, buildApiUrl }) => {
  if (typeof authorizedFetch !== "function") {
    throw new TypeError("authorizedFetch must be a function");
  }
  if (typeof buildApiUrl !== "function") {
    throw new TypeError("buildApiUrl must be a function");
  }

  const resolveUrl = () => buildApiUrl("schedule");

  return {
    load() {
      return authorizedFetch(resolveUrl());
    },
    save(payload) {
      const body = payload === undefined ? undefined : JSON.stringify(payload);
      return authorizedFetch(resolveUrl(), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body,
      });
    },
  };
};
