# Newshare Network Protocol Mapper (Keycloak SPI)

Custom Keycloak protocol mapper that adds Newshare Network claims to OIDC tokens.

## Claims Added

| Claim            | Source                          | Example               |
|------------------|---------------------------------|-----------------------|
| `networkUserId`  | `[homeBaseId]-[pairwise sub prefix]` | `HB001-a1b2c3d4e5f6` |
| `homeBaseId`     | Mapper configuration            | `HB001`               |
| `networkGroupId` | User attribute (integer bitmask)| `3`                   |
| `pubMbrId`       | Client attribute                | `PUB042`              |

## Prerequisites

- Java 17+
- Apache Maven 3.8+
- Keycloak 26.x
- The built-in **Pairwise Subject Identifier** mapper must be configured on the client (or client scope) first, so that `sub` contains the pairwise PPID before this mapper runs.

## Build

```bash
chmod +x build.sh
./build.sh
```

This produces `target/newshare-protocol-mapper-0.1.0.jar`.

## Install

1. Copy the JAR into the Keycloak providers directory:

   ```bash
   cp target/newshare-protocol-mapper-0.1.0.jar /opt/keycloak/providers/
   ```

2. Restart Keycloak so it discovers the new provider:

   ```bash
   docker compose restart keycloak
   ```

## Configure in Keycloak Admin

1. Navigate to **Realm Settings > Client Scopes** (or open the specific client).
2. Open the scope/client where you want the claims and go to the **Mappers** tab.
3. Click **Add mapper > By configuration** and select **Newshare Network User ID**.
4. Set the **Home Base ID** (defaults to `HB001`).
5. Ensure "Add to ID token", "Add to access token", and "Add to userinfo" are enabled as needed.
6. Save.

Make sure each user has a `networkGroupId` attribute set (integer bitmask) and each client has a `pubMbrId` attribute set in its client attributes.
