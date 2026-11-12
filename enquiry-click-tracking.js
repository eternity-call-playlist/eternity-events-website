/* Eternity Events: anonymous enquiry click events for existing GA4 tracking.
   Measures contact-link clicks, not confirmed enquiries or bookings.
   Does not transmit phone numbers, WhatsApp message text or customer details. */
(function () {
  "use strict";
  if (window.__eeEnquiryClicksInstalled) return;
  window.__eeEnquiryClicksInstalled = true;
  document.addEventListener("click", function (event) {
    var target = event.target;
    var anchor = target && target.closest ? target.closest("a[href]") : null;
    if (!anchor) return;
    var href = anchor.getAttribute("href") || "";
    var method = "";
    if (/^https?:\/\/(?:wa\.me|api\.whatsapp\.com)\//i.test(href)) method = "whatsapp";
    else if (/^tel:/i.test(href)) method = "phone";
    if (!method) return;
    if (typeof window.gtag !== "function") return;
    var id = "";
    var card = anchor.closest(".service-card");
    if (card) {
      var label = card.querySelector(".eyebrow");
      var match = label && label.textContent.match(/EE-\d{3}/i);
      if (match) id = match[0].toUpperCase();
    }
    if (!id) {
      var matchPage = window.location.pathname.match(/-ee-(\d{3})\.html$/i);
      if (matchPage) id = "EE-" + matchPage[1];
    }
    window.gtag("event", "contact_click", {
      contact_method: method,
      service_id: id || "general",
      page_path: window.location.pathname
    });
  }, false);
}());
