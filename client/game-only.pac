function FindProxyForURL(url, host) {
  host = host.toLowerCase();
  var domains = ["freefiremobile.com", "purplevioleto.com", "ppmainecoonghj.com"];
  for (var i = 0; i < domains.length; i++) {
    if (host === domains[i] || dnsDomainIs(host, "." + domains[i])) return "PROXY 159.223.110.159:1297";
  }
  return "DIRECT";
}
