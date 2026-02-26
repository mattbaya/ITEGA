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
 * Keycloak protocol mapper for the Newshare Network.
 *
 * Reads the pairwise {@code sub} that Keycloak already computed (via the
 * built-in SHA256PairwiseSubMapper) and adds four claims to every token:
 *
 * <ul>
 *   <li>{@code networkUserId} -- {@code [HomeBaseID]-[first 12 chars of pairwise sub]}</li>
 *   <li>{@code homeBaseId}    -- the network identifier of this Home Base</li>
 *   <li>{@code networkGroupId} -- integer bitmask from a user attribute</li>
 *   <li>{@code pubMbrId}      -- publisher member ID from a client attribute</li>
 * </ul>
 */
public class NewshareNetworkUserIdMapper extends AbstractOIDCProtocolMapper
        implements OIDCAccessTokenMapper, OIDCIDTokenMapper, UserInfoTokenMapper {

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

        // 2. Get the pairwise sub (already computed by Keycloak's built-in pairwise mapper)
        String pairwiseSub = token.getSubject();

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
                // Default to 0 (anonymous)
            }
        }
        token.getOtherClaims().put("networkGroupId", networkGroupId);

        // 7. Get pubMbrId from client attributes
        ClientModel client = clientSessionCtx.getClientSession().getClient();
        String pubMbrId = client.getAttribute(PUB_MBR_ID_ATTR);
        if (pubMbrId != null && !pubMbrId.isEmpty()) {
            token.getOtherClaims().put("pubMbrId", pubMbrId);
        }
    }
}
