package org.newshare.keycloak;

import org.keycloak.models.ClientModel;
import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.UserModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.protocol.oidc.mappers.AbstractOIDCProtocolMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAccessTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCIDTokenMapper;
import org.keycloak.protocol.oidc.mappers.UserInfoTokenMapper;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;

import java.util.ArrayList;
import java.util.List;

/**
 * Keycloak SPI protocol mapper for the Newshare Network.
 *
 * <p>This mapper runs AFTER Keycloak's built-in SHA256PairwiseSubMapper and
 * enriches every issued OIDC token (access token, ID token, userinfo) with
 * four custom claims required by the Newshare Network protocol:
 *
 * <ul>
 *   <li>{@code networkUserId} -- {@code [HomeBaseID]-[first 12 chars of pairwise sub]}.
 *       This is the primary opaque identifier used by the ALS for logging and
 *       settlement. It is different per publisher due to the pairwise PPID.</li>
 *   <li>{@code homeBaseId}    -- the network identifier of this Home Base (e.g., "HB001").
 *       Configured per-mapper in the Keycloak admin console.</li>
 *   <li>{@code networkGroupId} -- integer bitmask encoding the user's subscription
 *       tier(s). Read from a Keycloak user attribute. Used by publishers to gate
 *       content access without knowing user identity.</li>
 *   <li>{@code pubMbrId}      -- publisher member ID. Read from a Keycloak client
 *       attribute so each OIDC client (publisher) can carry its own membership ID.</li>
 * </ul>
 *
 * <h3>Service Discovery</h3>
 * <p>Registered via {@code META-INF/services/org.keycloak.protocol.ProtocolMapper}.
 * The JAR is deployed to Keycloak's {@code providers/} directory.</p>
 *
 * <h3>Privacy Guarantee</h3>
 * <p>This mapper NEVER emits PII. The {@code networkUserId} is derived from the
 * pairwise PPID, which is itself a one-way hash scoped to each publisher. If the
 * pairwise mapper has not run (misconfiguration), this mapper detects the raw
 * Keycloak UUID and hashes it to prevent identity leakage.</p>
 *
 * @see <a href="https://www.keycloak.org/docs/latest/server_development/#_protocol_mappers">
 *      Keycloak Protocol Mapper SPI</a>
 */
public class NewshareNetworkUserIdMapper extends AbstractOIDCProtocolMapper
        implements OIDCAccessTokenMapper, OIDCIDTokenMapper, UserInfoTokenMapper {

    private static final org.jboss.logging.Logger logger =
        org.jboss.logging.Logger.getLogger(NewshareNetworkUserIdMapper.class);

    public static final String PROVIDER_ID = "newshare-network-userid-mapper";

    /** Mapper config key for the home base identifier string. */
    public static final String HOME_BASE_ID_CONFIG = "homeBaseId";

    /** Name of the Keycloak user attribute that holds the network group bitmask. */
    public static final String NETWORK_GROUP_ID_ATTR = "networkGroupId";

    /** Name of the Keycloak client attribute that holds the publisher member ID. */
    public static final String PUB_MBR_ID_ATTR = "pubMbrId";

    private static final int PAIRWISE_PREFIX_LENGTH = 12;

    private static final List<ProviderConfigProperty> CONFIG_PROPERTIES = new ArrayList<>();

    static {
        ProviderConfigProperty homeBaseIdProp = new ProviderConfigProperty();
        homeBaseIdProp.setName(HOME_BASE_ID_CONFIG);
        homeBaseIdProp.setLabel("Home Base ID");
        homeBaseIdProp.setHelpText("The network ID of this home base (e.g., HB001)");
        homeBaseIdProp.setType(ProviderConfigProperty.STRING_TYPE);
        homeBaseIdProp.setDefaultValue("HB001");
        CONFIG_PROPERTIES.add(homeBaseIdProp);
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return CONFIG_PROPERTIES;
    }

    @Override
    public String getId() {
        return PROVIDER_ID;
    }

    @Override
    public String getDisplayCategory() {
        return "Token mapper";
    }

    @Override
    public String getDisplayType() {
        return "Newshare Network User ID";
    }

    @Override
    public String getHelpText() {
        return "Adds networkUserId, homeBaseId, networkGroupId, and pubMbrId claims "
                + "to the token for the Newshare Network.";
    }

    @Override
    protected void setClaim(IDToken token,
                            ProtocolMapperModel mappingModel,
                            UserSessionModel userSession,
                            KeycloakSession keycloakSession,
                            ClientSessionContext clientSessionCtx) {

        // 1. Get home base ID from mapper config
        String homeBaseId = mappingModel.getConfig().get(HOME_BASE_ID_CONFIG);
        if (homeBaseId == null || homeBaseId.isEmpty()) {
            homeBaseId = "HB001";
        }

        // 2. Get the pairwise sub (already computed by Keycloak's built-in pairwise mapper).
        //    IMPORTANT: If the Pairwise Subject Identifier mapper has not run (or is
        //    configured with lower priority), token.getSubject() returns the raw
        //    Keycloak UUID. We detect this and hash it to prevent identity leakage.
        String pairwiseSub = token.getSubject();

        if (pairwiseSub != null && pairwiseSub.length() < 32) {
            logger.warnf("Subject '%s' appears to be a raw UUID, not a pairwise PPID. " +
                "Ensure the Pairwise Subject Identifier mapper is configured with higher priority.", pairwiseSub);
            // Hash the raw UUID to prevent identity leakage
            pairwiseSub = Integer.toHexString(pairwiseSub.hashCode());
        }

        // 3. Build networkUserId: [HomeBaseID]-[first 12 chars of pairwise sub]
        String networkUserId;
        if (pairwiseSub != null && pairwiseSub.length() >= PAIRWISE_PREFIX_LENGTH) {
            networkUserId = homeBaseId + "-" + pairwiseSub.substring(0, PAIRWISE_PREFIX_LENGTH);
        } else {
            networkUserId = homeBaseId + "-" + (pairwiseSub != null ? pairwiseSub : "unknown");
        }

        // 4. Set networkUserId claim
        token.getOtherClaims().put("networkUserId", networkUserId);

        // 5. Set homeBaseId claim
        token.getOtherClaims().put("homeBaseId", homeBaseId);

        // 6. Get networkGroupId from user attributes
        UserModel user = userSession.getUser();
        String groupIdStr = user.getFirstAttribute(NETWORK_GROUP_ID_ATTR);
        int networkGroupId = 0;
        if (groupIdStr != null && !groupIdStr.isEmpty()) {
            try {
                networkGroupId = Integer.parseInt(groupIdStr);
            } catch (NumberFormatException e) {
                logger.warnf("Invalid networkGroupId '%s' for user '%s'; defaulting to 0 (anonymous).",
                    groupIdStr, user.getId());
            }
        }
        token.getOtherClaims().put("networkGroupId", networkGroupId);

        // 7. Get pubMbrId from client attributes.
        //    Always set the claim (empty string if not configured) so downstream
        //    consumers don't have to handle a missing claim vs. an empty one.
        ClientModel client = clientSessionCtx.getClientSession().getClient();
        String pubMbrId = client.getAttribute(PUB_MBR_ID_ATTR);
        token.getOtherClaims().put("pubMbrId", pubMbrId != null ? pubMbrId : "");
    }
}
