/**
 * networkGroupId.ts -- NetworkGroupId Bitmask Encoding/Decoding Utilities
 *
 * The NetworkGroupId is a custom claim embedded in the OIDC ID Token (JWT)
 * issued by the ALS. It uses a bitmask encoding scheme where each bit
 * position represents a subscription attribute or access tier:
 *
 *   Bit 1     (0x0001) = Group Account
 *   Bit 2     (0x0002) = Registered
 *   Bit 4     (0x0004) = Print Subscriber
 *   Bit 8     (0x0008) = Digital Subscriber
 *   Bit 16    (0x0010) = Data Subscriber
 *   Bit 1024  (0x0400) = Complimentary
 *   Bit 2048  (0x0800) = Controlled
 *   Bit 4096  (0x1000) = Paid
 *   Bit 8192  (0x2000) = Trial
 *   Bit 16384 (0x4000) = Site/Group
 *
 * Multiple bits can be set simultaneously. For example, a value of 4106
 * (4096 | 8 | 2) means "Paid + Digital Subscriber + Registered".
 *
 * Publishers use the NetworkGroupId to determine access rights without
 * knowing the user's real identity. The home base sets this value based
 * on the user's subscription status.
 */
const BIT_LABELS: Record<number, string> = {
  1: 'Group Account',
  2: 'Registered',
  4: 'Print Subscriber',
  8: 'Digital Subscriber',
  16: 'Data Subscriber',
  1024: 'Complimentary',
  2048: 'Controlled',
  4096: 'Paid',
  8192: 'Trial',
  16384: 'Site/Group',
};

/** Map of bit values to Tailwind color classes for badge rendering. */
export const BIT_COLORS: Record<number, string> = {
  1: 'bg-blue-100 text-blue-800',
  2: 'bg-gray-100 text-gray-800',
  4: 'bg-amber-100 text-amber-800',
  8: 'bg-indigo-100 text-indigo-800',
  16: 'bg-purple-100 text-purple-800',
  1024: 'bg-teal-100 text-teal-800',
  2048: 'bg-orange-100 text-orange-800',
  4096: 'bg-green-100 text-green-800',
  8192: 'bg-yellow-100 text-yellow-800',
  16384: 'bg-cyan-100 text-cyan-800',
};

export function decodeBitmask(groupId: number): string[] {
  return Object.entries(BIT_LABELS)
    .filter(([bit]) => (groupId & Number(bit)) !== 0)
    .map(([, label]) => label);
}

export function decodeBitmaskWithBits(
  groupId: number,
): Array<{ bit: number; label: string }> {
  return Object.entries(BIT_LABELS)
    .filter(([bit]) => (groupId & Number(bit)) !== 0)
    .map(([bit, label]) => ({ bit: Number(bit), label }));
}
