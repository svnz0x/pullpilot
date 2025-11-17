export const flushTasks = async (times = 1) => {
  for (let iteration = 0; iteration < times; iteration += 1) {
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
  }
};
