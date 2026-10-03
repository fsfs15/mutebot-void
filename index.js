const {
    Client,
    GatewayIntentBits,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    EmbedBuilder,
    MessageFlags
} = require('discord.js');
require('dotenv').config();

// ============================================================
// CONFIG (IDs inchangés)
// ============================================================

const MANAGER_ROLE = '1487206053392416961';
const PANEL_CHANNEL_ID = '1516210440672378971';

const ALLOWED_CHANNELS = [
    '1373282885712351333',
    '1373282902036713553',
    '1534797504820809801',
    '1535720878778876015'
];

const PANEL_TITLE = '🎙️ Contrôle Mute';
const PANEL_DESCRIPTION =
    '**Kifesh tekhdem:**\n' +
    '- 🔴 `Mute Kaml`: L\'bot ydir Mute l\'ga3 nas li m3ak f l\'salon.\n' +
    '- 🟢 `Unmute Kaml`: L\'bot yna7i l\'Mute 3la ga3 nas li m3ak f l\'salon.';

// ============================================================
// LOGGER
// ============================================================
// Logs structurés avec timestamp, jamais de handler vide.

const logger = {
    info: (...args) => console.log(`[INFO] ${new Date().toISOString()}`, ...args),
    warn: (...args) => console.warn(`[WARN] ${new Date().toISOString()}`, ...args),
    error: (...args) => console.error(`[ERROR] ${new Date().toISOString()}`, ...args)
};

if (typeof fetch !== 'function') {
    logger.error('fetch global introuvable. Node 18+ requis pour ce bot.');
    process.exit(1);
}

// ============================================================
// APPEL REST DIRECT (bypass volontaire de la queue @discordjs/rest)
// ============================================================
// discord.js sérialise les requêtes qui partagent le même bucket
// (PATCH /guilds/{id}/members/{id} est bucketé PAR GUILD, pas par membre) :
// il attend la réponse d'une requête avant d'envoyer la suivante.
// Résultat : même avec Promise.allSettled côté JS, les appels
// member.voice.setMute() finissent quasi séquentiels sur le réseau.
//
// Ici on appelle l'API Discord nous-mêmes pour que les requêtes
// partent VRAIMENT en parallèle. On respecte toujours les rate
// limits : si Discord répond 429, on lit le Retry-After réel et on
// ne réessaie QUE ce membre-là, sans jamais toucher aux autres.
const DISCORD_API_BASE = 'https://discord.com/api/v10';
const MAX_MUTE_RETRIES = 3;

async function setMemberMuteDirect(guildId, userId, mute, reason, attempt = 0) {
    const response = await fetch(`${DISCORD_API_BASE}/guilds/${guildId}/members/${userId}`, {
        method: 'PATCH',
        headers: {
            Authorization: `Bot ${process.env.DISCORD_TOKEN}`,
            'Content-Type': 'application/json',
            ...(reason ? { 'X-Audit-Log-Reason': encodeURIComponent(reason) } : {})
        },
        body: JSON.stringify({ mute })
    });

    if (response.status === 429) {
        if (attempt >= MAX_MUTE_RETRIES) {
            throw new Error(`Rate limit persistant après ${MAX_MUTE_RETRIES} tentatives pour ${userId}`);
        }
        const body = await response.json().catch(() => ({}));
        const retryAfterMs = Math.ceil((body.retry_after ?? 1) * 1000);
        logger.warn(`429 pour ${userId}, retry dans ${retryAfterMs}ms (tentative ${attempt + 1}/${MAX_MUTE_RETRIES})`);
        await new Promise((resolve) => setTimeout(resolve, retryAfterMs));
        return setMemberMuteDirect(guildId, userId, mute, reason, attempt + 1);
    }

    if (!response.ok) {
        const errorBody = await response.text().catch(() => '');
        throw new Error(`Discord API ${response.status} pour ${userId}: ${errorBody}`);
    }

    return true;
}

// ============================================================
// CLIENT
// ============================================================

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildVoiceStates
    ]
});

// Verrou PAR salon vocal (pas un boolean global).
// Une opération dans le salon A ne bloque jamais le salon B.
const processingChannels = new Set();

// ============================================================
// PANEL (création / mise à jour, jamais de doublon)
// ============================================================

async function createOrUpdatePanel() {
    try {
        const channel = await client.channels.fetch(PANEL_CHANNEL_ID);
        if (!channel) {
            logger.error('Panel channel introuvable:', PANEL_CHANNEL_ID);
            return;
        }

        const embed = new EmbedBuilder()
            .setTitle(PANEL_TITLE)
            .setDescription(PANEL_DESCRIPTION)
            .setColor('#2b2d31');

        const row = new ActionRowBuilder().addComponents(
            new ButtonBuilder().setCustomId('mute_all').setLabel('🔇 Mute Kaml').setStyle(ButtonStyle.Danger),
            new ButtonBuilder().setCustomId('unmute_all').setLabel('🔊 Unmute Kaml').setStyle(ButtonStyle.Success)
        );

        const messages = await channel.messages.fetch({ limit: 10 });
        const existingPanel = messages.find(
            (m) => m.author.id === client.user.id && m.embeds.length > 0 && m.embeds[0].title === PANEL_TITLE
        );

        if (existingPanel) {
            await existingPanel.edit({ embeds: [embed], components: [row] });
            logger.info('Panel existant mis à jour.');
        } else {
            await channel.send({ embeds: [embed], components: [row] });
            logger.info('Nouveau panel créé.');
        }
    } catch (error) {
        logger.error("Impossible de créer/mettre à jour le panel:", error);
    }
}

// ============================================================
// VALIDATION
// ============================================================

/**
 * Vérifie rôle Manager, présence en vocal, salon autorisé, et double-lock.
 * Répond directement à l'interaction en cas d'échec.
 * @returns {import('discord.js').VoiceChannel|null} le salon vocal si tout est valide, sinon null.
 */
async function validateInteraction(interaction) {
    if (!interaction.member.roles.cache.has(MANAGER_ROLE)) {
        await interaction.reply({
            content: "⛔ Manager bark li ya9dar ydir hadi.",
            flags: MessageFlags.Ephemeral
        });
        return null;
    }

    const voiceChannel = interaction.member.voice.channel;
    if (!voiceChannel) {
        await interaction.reply({
            content: "⛔ Lazm tkoun dakhil l'salon vocal bash tsta3mel l'Panel!",
            flags: MessageFlags.Ephemeral
        });
        return null;
    }

    if (!ALLOWED_CHANNELS.includes(voiceChannel.id)) {
        await interaction.reply({
            content: "⛔ L'bot ma ykhdmch f had l'salon vocal.",
            flags: MessageFlags.Ephemeral
        });
        return null;
    }

    if (processingChannels.has(voiceChannel.id)) {
        await interaction.reply({
            content: "⚠️ Une opération est déjà en cours dans ce salon.",
            flags: MessageFlags.Ephemeral
        });
        return null;
    }

    return voiceChannel;
}

// ============================================================
// TRAITEMENT DES MEMBRES (coeur de l'optimisation)
// ============================================================

/**
 * Applique setMute(muteState) à tous les membres ciblés, en parallèle contrôlé.
 * Aucun délai artificiel : discord.js gère la file d'attente et les rate limits.
 * Une erreur sur un membre n'affecte jamais les autres (Promise.allSettled).
 */
async function processVoiceMembers(voiceChannel, muteState, reason) {
    const allMembers = Array.from(voiceChannel.members.values());

    // On ne traite que les membres qui ont réellement besoin d'un changement.
    const targetMembers = allMembers.filter((member) => member.voice.serverMute !== muteState);

    const guildId = voiceChannel.guild.id;
    const startedAt = Date.now();

    const results = await Promise.allSettled(
        targetMembers.map((member) => setMemberMuteDirect(guildId, member.id, muteState, reason))
    );

    const durationSeconds = ((Date.now() - startedAt) / 1000).toFixed(2);

    let succeeded = 0;
    let failed = 0;

    results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
            succeeded++;
        } else {
            failed++;
            const member = targetMembers[index];
            logger.error(
                `Echec setMute(${muteState}) pour ${member?.user?.tag ?? member?.id ?? 'inconnu'}:`,
                result.reason
            );
        }
    });

    return {
        found: allMembers.length,
        targeted: targetMembers.length,
        succeeded,
        failed,
        durationSeconds
    };
}

// ============================================================
// RÉSUMÉ FINAL
// ============================================================

async function sendOperationResult(interaction, muteState, stats) {
    const isMute = muteState === true;

    const embed = new EmbedBuilder()
        .setTitle(isMute ? '🔇 Mute terminé' : '🔊 Unmute terminé')
        .setColor(isMute ? '#e74c3c' : '#2ecc71')
        .addFields(
            { name: '👥 Membres trouvés', value: `${stats.found}`, inline: true },
            { name: isMute ? '✅ Membres mutés' : '✅ Membres unmuted', value: `${stats.succeeded}`, inline: true },
            { name: '⚠️ Échecs', value: `${stats.failed}`, inline: true },
            { name: '⏱️ Durée', value: `${stats.durationSeconds}s`, inline: true }
        );

    try {
        await interaction.editReply({ content: null, embeds: [embed] });
    } catch (error) {
        // Interaction expirée (>15 min) ou autre souci réseau : on log, on ne bloque rien.
        logger.error("Impossible d'envoyer le résumé (interaction probablement expirée):", error);
    }
}

// ============================================================
// HANDLER PRINCIPAL: mute / unmute
// ============================================================

async function handleMuteAction(interaction, muteState) {
    const voiceChannel = await validateInteraction(interaction);
    if (!voiceChannel) return;

    processingChannels.add(voiceChannel.id);

    try {
        await interaction.reply({
            content: muteState
                ? '🔴 L\'Mute bda! (Rah yt\'aplica b ndam, sans délai)'
                : '🟢 L\'Unmute bda! (Rah yt\'aplica b ndam, sans délai)',
            flags: MessageFlags.Ephemeral
        });

        const reason = `${muteState ? 'Mute Kaml' : 'Unmute Kaml'} - par ${interaction.user.tag}`;
        const stats = await processVoiceMembers(voiceChannel, muteState, reason);

        await sendOperationResult(interaction, muteState, stats);
    } catch (error) {
        logger.error(`Erreur pendant l'opération ${muteState ? 'mute' : 'unmute'} sur le salon ${voiceChannel.id}:`, error);
        try {
            await interaction.editReply({ content: "❌ Une erreur inattendue est survenue pendant l'opération." });
        } catch (innerError) {
            logger.error("Impossible d'éditer la réponse après erreur:", innerError);
        }
    } finally {
        // Le verrou est TOUJOURS retiré, même en cas d'erreur.
        processingChannels.delete(voiceChannel.id);
    }
}

// ============================================================
// EVENTS
// ============================================================

client.once('ready', async () => {
    logger.info(`Bot connecté: ${client.user.tag}`);
    await createOrUpdatePanel();
});

client.on('interactionCreate', async (interaction) => {
    if (!interaction.isButton()) return;

    try {
        if (interaction.customId === 'mute_all') {
            await handleMuteAction(interaction, true);
        } else if (interaction.customId === 'unmute_all') {
            await handleMuteAction(interaction, false);
        }
    } catch (error) {
        logger.error('Erreur non gérée dans interactionCreate:', error);
    }
});

// ============================================================
// GESTION DES ERREURS GLOBALES (jamais de handler vide)
// ============================================================

process.on('unhandledRejection', (error) => {
    logger.error('[Unhandled Rejection]', error);
});

process.on('uncaughtException', (error) => {
    logger.error('[Uncaught Exception]', error);
});

client.login(process.env.DISCORD_TOKEN);