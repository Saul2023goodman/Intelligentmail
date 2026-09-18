import type { MailboxGateway, MailboxSummary } from "./types";

export type GatewayState =
  | "unavailable"
  | "disconnected"
  | "mismatch"
  | "connected";

export type GatewayHealth = {
  state: GatewayState;
  /** Address the extension bridge is currently connected to. */
  connectedAddress: string;
  /** The selected Student's registered mailbox. */
  studentAddress: string;
  /** Whether observation can run for the selected Student right now. */
  canObserve: boolean;
  /** True only for a connected adapter that supports the gateway. */
  enabled: boolean;
};

/**
 * Derive Mailbox Gateway health from existing Core data: the live bridge
 * connection plus one Student's registered mailbox. Pure presentation of Core
 * state; no page owns this decision.
 */
export function gatewayHealth(
  gateway: MailboxGateway | undefined,
  student: MailboxSummary | null,
): GatewayHealth {
  const studentAddress = (student?.address || "").toLowerCase();
  const connectedAddress = (gateway?.mailbox_address || "").toLowerCase();
  const enabled = Boolean(
    gateway && gateway.adapter !== "unavailable" && gateway.adapter !== "disabled",
  );
  if (!enabled) {
    return {
      state: "unavailable",
      connectedAddress,
      studentAddress,
      canObserve: false,
      enabled: false,
    };
  }
  if (!gateway?.connected || !connectedAddress) {
    return {
      state: "disconnected",
      connectedAddress: "",
      studentAddress,
      canObserve: false,
      enabled: true,
    };
  }
  if (studentAddress && connectedAddress !== studentAddress) {
    return {
      state: "mismatch",
      connectedAddress,
      studentAddress,
      canObserve: false,
      enabled: true,
    };
  }
  return {
    state: "connected",
    connectedAddress,
    studentAddress,
    canObserve: Boolean(studentAddress),
    enabled: true,
  };
}
