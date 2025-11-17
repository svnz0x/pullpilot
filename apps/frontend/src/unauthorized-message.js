export const buildUnauthorizedTokenMessage = (
  baseMessage,
  { reusableToken = false, hadMemoryToken = false, storageOutcome = null } = {},
) => {
  const normalizedMessage =
    typeof baseMessage === "string" && baseMessage.trim().length
      ? baseMessage.trim()
      : "";

  const reuseSuffix =
    "El token guardado se reutilizará automáticamente cuando el servidor vuelva a aceptar credenciales.";
  const reenterSuffix = "Introduce de nuevo el token para continuar.";

  let finalMessage = normalizedMessage;

  if (reusableToken) {
    finalMessage = normalizedMessage ? `${normalizedMessage} ${reuseSuffix}` : reuseSuffix;
  } else if (hadMemoryToken) {
    finalMessage = normalizedMessage ? `${normalizedMessage} ${reenterSuffix}` : reenterSuffix;
  }

  if (storageOutcome?.handled && storageOutcome.message) {
    const storageMessage = storageOutcome.message.trim();
    if (storageMessage) {
      finalMessage = finalMessage ? `${finalMessage} ${storageMessage}` : storageMessage;
    }
  }

  return finalMessage;
};

export default buildUnauthorizedTokenMessage;
