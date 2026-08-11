import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";
import { getAppMessages } from "./messages";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = requested && hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  return {
    locale,
    messages: getAppMessages(locale),
  };
});
