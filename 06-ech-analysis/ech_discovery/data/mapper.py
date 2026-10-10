from enum import StrEnum
from ech_discovery import config
from ech_discovery.data.columns import Columns as C
import seaborn as sns
import polars as pl


class Strings(StrEnum):
    ts = "Time YYYY-MM-DD HH:MM"
    domains = "Domains [#]"
    domains_toplist = "Unique Second-Level\nDomain Names on\nAggregated Toplists [#]"
    failures = "Failures [#]"
    failures_percent = "Failures [%]"
    failure = "Failure"
    probing = "ECH-Enabled"
    ech_in_dns = "ECH in DNS"
    ech_in_https = "ECH in HTTPS RRs"
    second_level_domains = "Second-Level Domains [#]"

    domain_name_length = "Max Domain Length [#]"
    ech_public_name_length = "ECH Public Name Length [#]"
    ech_public_name = "ECH Public Name"

    measurement_start_time = "Measurement Start Time"
    configurations = "Configurations [#]"
    ech_public_names = "Public Names [#]"
    ech_public_keys = "Public Keys [#]"
    ech_max_name_len = "Max Name Length [chars]"
    ech_key_rotation_interval = "Rotation Interval [h]"
    ech_key_grace_period = "Grace Period [h]"
    configurations_wrapped = "Config- urations [#]"
    transport = "Transport"
    transport_tcp = "TCP"
    transport_quic = "QUIC"
    transport_tcp_col = "Transport TCP"
    transport_quic_col = "Transport QUIC"
    location = "Location"

    # ECH deployment configuration table (configurations/03)
    ech_config_id = "Config ID"
    outer_ech_config_id = "ECH Config ID"
    outer_sni = "SNI"
    outer_ch_variation = "Outer CH Variation"
    ech_configurations = "ECH Configurations"
    general = "General"
    ech_key = "Key"

    # Coverage of ECH configurations in DNS across a deployment's domains
    coverage_all = "all"
    coverage_partial = "partial"
    coverage_none = "none"

    domains_subsequent_ech = "Stability of ECH-\ncapable domains [%]"
    configuration_variation_accepted = "Accepted Config Variation"

    domain_names = "Unique Second-Level Domain Names [#]"
    unique_second_level = "Unique Second-Level"
    probed_domains = "Probed Domains"
    domain_names_linebreak = "Unique Second-Level\nDomain Names [#]"
    domain_connections = "Connections [#]"
    public_name_short = "Public Name"
    public_name_split = "ECH Public\nName"
    yes = "Yes"
    no = "No"
    tls_hs_duration = "TLS Handshake Duration [ms]"
    tls_hs_type = "Handshake"
    hs_type_no_ech = "TLS 1.3"
    hs_type_ech = "TLS 1.3 + ECH"
    hs_type_diff = "TLS 1.3 - (TLS 1.3 + ECH)"
    proportion = "Proportion"
    delay = "Delay [ms]"

    not_available = "n/a"
    quic_error = "QUIC error"
    end_of_grace_period = "end of grace period"

    latex_cmark = r"\cmark"
    latex_cmark_partial = r"(\cmark)"
    latex_xmark = r"\xmark"
    latex_retry_config = r"$\circlearrowleft$"
    latex_tls_alert = r"\textcircled{\small !}"

    # TLS-Attacker comparison table (related-work/02)
    tls_library = "TLS library"
    webserver = "Webserver"
    version = "Version"
    released = "Released"
    result = "Result"
    code_support = "Code Support"
    ech_configured = "ECH Configured"
    niere_et_al = "Niere et al."
    server_configuration = "Server Configuration"
    ech_detected = "ECH Detected"
    niere_unknown_extension = (
        "Unparsacble ECH configuration in TLS grease extension (cf. Niere et al.) "
    )
    unparsable_ech_extension = "Unparsable ECH extension (cf. Niere et al.)"
    parsable_ech_extension = "Parsable ECH extension (this work)"
    apache_httpd = "Apache httpd"
    openssl3_ech = "OpenSSL3 with ECH (defo fork)"
    openssl3 = "OpenSSL3"
    boringssl = "BoringSSL"

    # Related work literature table
    paper = "Paper"
    year = "Year"
    this_work = "This Work"
    this_work_citekey = "This work"
    esni_ech_connection = "ESNI/ECH Connection"
    detection_without_dns = "Detection without DNS"

    config_id_colors = "Colors indicate ECH configuration IDs"
    cum_latency = "Cumulated Domains [%]"
    latency = "Domains [%]"
    others = "Others"


class EchtoolErrorKind(StrEnum):
    accepted = "accepted"
    ech_rejected = "ech_rejected"
    no_retry_config = "no_retry_config"
    network_error = "network_error"
    dns_error = "dns_error"

    certificate_error = "certificate_error"
    quic_invalid_token = "quic_invalid_token"
    tls_alert = "tls_alert"
    handshake_failure = "handshake_failure"
    ech_rejected_with_retry = "ech_rejected_with_retry"


class EchtoolSource(StrEnum):
    dns = "dns"
    retry = "retry"
    probe = "probe"


ech_dns_rr_map = {True: "With ECH Configuration in DNS", False: "No ECH Configuration in DNS"}
ech_dns_rr_map_linebreaks = {
    True: "With ECH Configuration\nin DNS",
    False: "No ECH Configuration in DNS",
}

role_map = {"ech": "TCP+TLS", "ech-quic": "QUIC", "ech-zdns": "HTTPS RRs"}

region_map = {
    "tud": "TU Dresden, DE",
    "africa-south1": "ZA, AF",
    "us-west2": "US, NA",
    "europe-west10": "DE, EU",
    "australia-southeast1": "AU, AU",
    "southamerica-east1": "BR, SA",
    "asia-east2": "HK, AS",
}

ech_public_name_cmap = {
    config.PUBLIC_NAME_CLOUDFLARE: sns.color_palette("tab10")[1],
    config.PUBLIC_NAME_META: sns.color_palette("tab10")[0],
}


akamai_as = [
    21399,
    43639,
    33905,
    55770,
    55409,
    23903,
    20940,
    21342,
    16625,
    31377,
    35204,
    39836,
    33047,
    31109,
    34164,
    21357,
    34850,
    17204,
    31107,
    31110,
    393560,
    24319,
    12222,
    31108,
    36183,
]
netflix_as = [40027, 2906]
fastly_as = [
    394192,
    895,
    54113,
    149097,
]
microsoft_as = [
    45139,
    398656,
    398575,
    20046,
    395851,
    395496,
    395524,
    396463,
    3598,
    14719,
    13399,
    6182,
    8068,
    5761,
    6291,
    23468,
    52985,
    6584,
    35106,
    12076,
    8075,
]
limelight_edgio_as = [
    60261,
    45396,
    38622,
    38621,
    12411,
    27191,
    25804,
    55429,
    23059,
    23164,
    23135,
    26506,
    22822,
]
apple_as = [1042, 1036, 714, 63707, 6185]
twitter_as = [54888, 13414]
amazon_as = [
    16509,
    14618,
    10124,
    17493,
    38895,
    7224,
    58588,
    135630,
    8987,
    62785,
    801,
    699,
]
youtube_as = [1026, 11344, 43515]

facebook_as = [149642, 54115, 63293, 32934]
google_as = [
    36492,
    15169,
    16550,
    36384,
    41264,
    6432,
    45566,
    24424,
    55023,
    396982,
    32381,
    26910,
    36987,
    139070,
    19527,
    26684,
    200238,
]
cloudflare_as = [13335, 132892, 14789, 202623, 395747, 394536, 203898, 209242]
f5_as = [35280, 22317]
aws_as = [
    19047,
    36263,
    40045,
]
cachefly_as = [30081]
edgecast_as = [
    14153,
]
bunny_as = [200325]


cdns = {
    "Akamai": akamai_as,
    "Netflix": netflix_as,
    "Fastly": fastly_as,
    "Microsoft": microsoft_as,
    "LimelightEdgio": limelight_edgio_as,
    "Apple": apple_as,
    "Twitter": twitter_as,
    "Amazon": amazon_as,
    "Youtube": youtube_as,
    "Cloudflare": cloudflare_as,
    "Meta": facebook_as,
    "Google": google_as,
    "F5": f5_as,
    "AWS": aws_as,
    "CacheFly": cachefly_as,
    "EdgeCast": edgecast_as,
    "Bunny": bunny_as,
}
df_cdns = (
    pl.DataFrame(
        {
            C.asn_cdn: list(cdns.keys()),
            C.asn: list(cdns.values()),
        }
    ).explode(C.asn, empty_as_null=True)
).with_columns(pl.col(C.asn).cast(pl.UInt32))
