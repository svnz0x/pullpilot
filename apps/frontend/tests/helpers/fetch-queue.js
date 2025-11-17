export const createFetchQueue = () => {
  const queue = [];

  const enqueueResponses = (responses = []) => {
    queue.push(
      ...responses.map((factory) => async (input, init) => {
        const result = typeof factory === "function" ? factory(input, init) : factory;
        return result instanceof Promise ? result : Promise.resolve(result);
      }),
    );
  };

  const fetchStub = async (input, init = {}) => {
    if (queue.length === 0) {
      const target = typeof input === "object" && input !== null ? input.url ?? "object" : input;
      throw new Error(`Unexpected fetch for ${target}`);
    }
    const handler = queue.shift();
    return handler(input, init);
  };

  const okResponse = (body) =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

  return { fetch: fetchStub, enqueueResponses, okResponse, queue };
};
