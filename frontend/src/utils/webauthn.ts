type AnyObject = Record<string, any>;

export function isPasskeySupported() {
  return typeof window !== "undefined" && window.isSecureContext && "PublicKeyCredential" in window && !!window.PublicKeyCredential;
}

export function isPasskeyAbortError(error: unknown) {
  const item = error as { name?: string; message?: string; code?: number } | null | undefined;
  const name = item?.name || "";
  const message = item?.message || "";
  return (
    name === "NotAllowedError" ||
    name === "AbortError" ||
    item?.code === 20 ||
    message.includes("timed out") ||
    message.includes("not allowed") ||
    message.includes("privacy-considerations-client")
  );
}

function base64UrlToBytes(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "===".slice((normalized.length + 3) % 4);
  const raw = atob(padded);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) {
    bytes[i] = raw.charCodeAt(i);
  }
  return bytes;
}

function bytesToBase64Url(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function toArrayBuffer(value: string | Uint8Array | ArrayBuffer) {
  if (value instanceof ArrayBuffer) return value;
  if (value instanceof Uint8Array) return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength);
  return base64UrlToBytes(value).buffer;
}

function normalizeValue(value: any): any {
  if (value instanceof ArrayBuffer) return bytesToBase64Url(new Uint8Array(value));
  if (ArrayBuffer.isView(value)) {
    const view = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    return bytesToBase64Url(view);
  }
  if (Array.isArray(value)) return value.map(normalizeValue);
  if (value && typeof value === "object") {
    const next: AnyObject = {};
    Object.entries(value).forEach(([key, item]) => {
      next[key] = normalizeValue(item);
    });
    return next;
  }
  return value;
}

export function normalizeCreationOptions(options: AnyObject) {
  return {
    ...options,
    challenge: toArrayBuffer(options.challenge),
    user: {
      ...options.user,
      id: toArrayBuffer(options.user?.id || ""),
    },
    excludeCredentials: (options.excludeCredentials || []).map((item: AnyObject) => ({
      ...item,
      id: toArrayBuffer(item.id),
    })),
  } as PublicKeyCredentialCreationOptions;
}

export function normalizeRequestOptions(options: AnyObject) {
  return {
    ...options,
    challenge: toArrayBuffer(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((item: AnyObject) => ({
      ...item,
      id: toArrayBuffer(item.id),
    })),
  } as PublicKeyCredentialRequestOptions;
}

export function credentialToJSON(credential: Credential | PublicKeyCredential | null) {
  if (!credential) return null;
  const publicKeyCredential = credential as PublicKeyCredential;
  const response = publicKeyCredential.response as AuthenticatorAttestationResponse | AuthenticatorAssertionResponse | undefined;
  const responsePayload: AnyObject = {};
  if (response) {
    if ("clientDataJSON" in response) responsePayload.clientDataJSON = normalizeValue(response.clientDataJSON);
    if ("attestationObject" in response) responsePayload.attestationObject = normalizeValue(response.attestationObject);
    if ("authenticatorData" in response) responsePayload.authenticatorData = normalizeValue(response.authenticatorData);
    if ("signature" in response) responsePayload.signature = normalizeValue(response.signature);
    if ("userHandle" in response) responsePayload.userHandle = normalizeValue(response.userHandle);
    if ("getTransports" in response) responsePayload.transports = response.getTransports();
  }
  return normalizeValue({
    id: credential.id,
    type: credential.type,
    rawId: publicKeyCredential.rawId,
    response: responsePayload,
    clientExtensionResults: publicKeyCredential.getClientExtensionResults(),
  });
}
