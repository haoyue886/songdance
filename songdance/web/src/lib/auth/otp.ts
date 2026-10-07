export const EMAIL_OTP_PATTERN = "[0-9]{6}(?:[0-9]{2})?";
export const EMAIL_OTP_MAX_LENGTH = 8;

const EMAIL_OTP = new RegExp(`^${EMAIL_OTP_PATTERN}$`);

export function isEmailOtp(value: unknown): value is string {
  return typeof value === "string"
    && (value.length === 6 || value.length === 8)
    && EMAIL_OTP.test(value);
}
