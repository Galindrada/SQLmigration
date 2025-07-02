//

// --- Negotiation Modal Logic ---
let currentDeal = null;
let playerIdForNegotiation = null;
let userTeamPlayers = []; // TODO: Populate with user's team players for smarter CPU counter-offers
let userId = window.currentUserId || null; // Set this in your base.html if not already

function renderDeal(deal) {
    let html = `<div><strong>${deal.club_name ? deal.club_name : 'CPU'} Demands:</strong></div>`;
    html += `<div>Cash Payment: <strong>€${deal.cash_paid.toLocaleString()}</strong></div>`;
    if (deal.player_given) {
        html += `<div>+ Your Player: <strong>${deal.player_given.NAME}</strong> (MV: €${deal.player_given['Market Value'].toLocaleString()})</div>`;
    }
    if (deal.cpu_player_given) {
        html += `<div>+ ${deal.club_name ? deal.club_name : 'CPU'} Offers: <strong>${deal.cpu_player_given.NAME}</strong> (MV: €${deal.cpu_player_given['Market Value'].toLocaleString()})</div>`;
    }
    return html;
}

function setDealButtonsEnabled(enabled) {
    $('#acceptDealBtn').prop('disabled', !enabled);
    $('#counterOfferBtn').prop('disabled', !enabled);
}

function fetchUserTeamPlayers(callback) {
    if (!userId) { callback([]); return; }
    $.ajax({
        url: `/get_team_players_full/${userId}`,
        method: 'GET',
        success: function(players) { callback(players); },
        error: function() { callback([]); }
    });
}

$('#negotiateModal').on('show.bs.modal', function (event) {
    const button = $(event.relatedTarget);
    playerIdForNegotiation = button.data('player-id');
    currentDeal = null;
    setDealButtonsEnabled(false);
    // Set modal header to loading first
    $('#negotiateModalLabel').text('Negotiation for ...');
    $('#negotiationContent').html('<div class="text-center text-muted">Loading initial offer...</div>');
    fetchUserTeamPlayers(function(players) {
        userTeamPlayers = players;
        // Fetch initial CPU demand
        $.ajax({
            url: `/negotiate_with_cpu/${playerIdForNegotiation}`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ user_team_players: userTeamPlayers }),
            success: function(resp) {
                currentDeal = resp.deal;
                // Set modal header to include player name if available
                if (resp.player_name) {
                    $('#negotiateModalLabel').text('Negotiation for (' + resp.player_name + ')');
                }
                $('#negotiationContent').html(renderDeal(currentDeal));
                setDealButtonsEnabled(true);
            },
            error: function() {
                $('#negotiationContent').html('<div class="text-danger">Error loading negotiation. Please try again.</div>');
                setDealButtonsEnabled(false);
            }
        });
    });
});

$('#acceptDealBtn').on('click', function() {
    if (!playerIdForNegotiation || !currentDeal) return;
    setDealButtonsEnabled(false);
    $('#negotiationContent').html('<div class="text-center text-muted">Finalizing deal...</div>');
    console.log('Accepting deal:', currentDeal);
    $.ajax({
        url: `/negotiate_with_cpu/${playerIdForNegotiation}`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            action: 'accept',
            current_deal: currentDeal,
            user_team_players: userTeamPlayers
        }),
        success: function(resp) {
            if (resp.success) {
                $('#negotiationContent').html('<div class="alert alert-success">' + resp.message + '</div>' +
                    '<button id="confirmTransferBtn" class="btn btn-success mt-3">Confirm Transfer</button>');
                if (resp.updated_budget !== undefined && $("#user-budget").length) {
                    $("#user-budget").text(resp.updated_budget.toLocaleString('en-US'));
                }
                $('#confirmTransferBtn').on('click', function() {
                    $.ajax({
                        url: `/confirm_transfer_with_cpu/${playerIdForNegotiation}`,
                        method: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify({ current_deal: currentDeal }),
                        success: function(resp2) {
                            if (resp2.success) {
                                $('#negotiationContent').html('<div class="alert alert-success">' + resp2.message + '</div>');
                                setTimeout(function() { location.reload(); }, 1200);
                            } else {
                                $('#negotiationContent').html('<div class="alert alert-danger">' + (resp2.error || 'Unknown error') + '</div>');
                            }
                        },
                        error: function() {
                            $('#negotiationContent').html('<div class="alert alert-danger">Error confirming transfer. Please try again.</div>');
                        }
                    });
                });
            } else {
                $('#negotiationContent').html('<div class="alert alert-danger">' + (resp.error || 'Unknown error') + '</div>');
            }
            setDealButtonsEnabled(false);
        },
        error: function() {
            $('#negotiationContent').html('<div class="alert alert-danger">Error completing deal. Please try again.</div>');
            setDealButtonsEnabled(false);
        }
    });
});

$('#counterOfferBtn').on('click', function() {
    if (!playerIdForNegotiation || !currentDeal) return;
    setDealButtonsEnabled(false);
    $('#negotiationContent').html('<div class="text-center text-muted">Negotiating...</div>');
    $.ajax({
        url: `/negotiate_with_cpu/${playerIdForNegotiation}`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            action: 'counter',
            current_deal: currentDeal,
            user_team_players: userTeamPlayers
        }),
        success: function(resp) {
            if (resp.step === 'cpu_quit') {
                $('#negotiationContent').html(`<div class="text-danger">${resp.message}</div>`);
                setDealButtonsEnabled(false);
                return;
            }
            if (resp.deal) {
                currentDeal = resp.deal;
                $('#negotiationContent').html(renderDeal(currentDeal));
                setDealButtonsEnabled(true);
            } else {
                $('#negotiationContent').html('<div class="text-danger">Negotiation ended or error.</div>');
                setDealButtonsEnabled(false);
            }
        },
        error: function() {
            $('#negotiationContent').html('<div class="text-danger">Error negotiating with CPU.</div>');
            setDealButtonsEnabled(false);
        }
    });
});

$('#negotiateModal').on('hidden.bs.modal', function () {
    currentDeal = null;
    playerIdForNegotiation = null;
    setDealButtonsEnabled(false);
    $('#negotiationContent').html('<div class="text-center text-muted">Negotiation logic coming soon...</div>');
});

// --- AJAX Offer Acceptance for Inbox ---
$(document).on('submit', 'form[action^="/offer/"][action$="/accept"]', function(e) {
    e.preventDefault();
    var $form = $(this);
    var $row = $form.closest('tr');
    var offerId = $form.attr('action').match(/offer\/(\d+)\/accept/)[1];
    $.ajax({
        url: $form.attr('action'),
        method: 'POST',
        dataType: 'json',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        success: function(resp) {
            if (resp.success) {
                // Update budget if element exists
                if (resp.updated_budget !== undefined && $("#user-budget").length) {
                    $("#user-budget").text(resp.updated_budget.toLocaleString('en-US'));
                }
                // Update offer row/status
                $row.find('td:eq(2)').text('Accepted');
                $row.find('td:eq(3)').html('Accepted');
            } else {
                alert(resp.error || 'Error accepting offer.');
            }
        },
        error: function(xhr) {
            let msg = 'Error accepting offer.';
            if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
            alert(msg);
        }
    });
});
