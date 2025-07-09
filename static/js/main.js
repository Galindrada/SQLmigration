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
            error: function(xhr) {
                if (xhr.status === 403) {
                    $('#negotiationContent').html('<div class="alert alert-warning">This player is no longer available for negotiation with you.</div>');
                } else {
                    $('#negotiationContent').html('<div class="text-danger">Error loading negotiation. Please try again.</div>');
                }
                setDealButtonsEnabled(false);
            }
        });
    });
});

$('#acceptDealBtn').on('click', function() {
    if (!playerIdForNegotiation || !currentDeal) return;
    setDealButtonsEnabled(false);
    // Show a final confirmation summary before executing the transfer
    let summaryHtml = '<div class="alert alert-info">';
    summaryHtml += '<h5>Confirm Transfer</h5>';
    let fromClub = currentDeal.club_name ? currentDeal.club_name : 'CPU';
    let toClub = window.userTeamName || 'Your Team';
    let cash = currentDeal.cash_paid || 0;
    let playerA = currentDeal.cpu_player_given ? currentDeal.cpu_player_given.NAME : null;
    let playerB = currentDeal.player_given ? currentDeal.player_given.NAME : null;
    summaryHtml += `<p>Confirm the transfer from <strong>${fromClub}</strong> of <strong>€${cash.toLocaleString()}</strong>`;
    if (playerA) summaryHtml += ` + <strong>${playerA}</strong>`;
    summaryHtml += ` to <strong>${toClub}</strong>`;
    if (playerB) summaryHtml += ` + <strong>${playerB}</strong>`;
    summaryHtml += '?</p>';
    summaryHtml += '</div>';
    summaryHtml += '<button id="finalConfirmTransferBtn" class="btn btn-success mt-3">Confirm Transfer</button>';
    $('#negotiationContent').html(summaryHtml);
    $('#finalConfirmTransferBtn').on('click', function() {
        $('#negotiationContent').html('<div class="text-center text-muted">Executing transfer...</div>');
        console.log('Sending transfer data:', { current_deal: currentDeal });
        $.ajax({
            url: `/confirm_transfer_with_cpu/${playerIdForNegotiation}`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ current_deal: currentDeal }),
            success: function(resp2) {
                console.log('Transfer response:', resp2);
                if (resp2.success) {
                    $('#negotiationContent').html('<div class="alert alert-success">' + resp2.message + '</div>');
                    setTimeout(function() { location.reload(); }, 1500);
                } else {
                    $('#negotiationContent').html('<div class="alert alert-danger">' + (resp2.error || 'Unknown error') + '</div>');
                }
            },
            error: function(xhr, status, error) {
                console.error('Transfer error:', xhr.responseText);
                $('#negotiationContent').html('<div class="alert alert-danger">Error confirming transfer. Please try again.</div>');
            }
        });
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

// --- AJAX Deal Confirmation for CPU Offers ---
let currentDealConfirmation = null;

$(document).on('click', '.confirm-deal-btn', function(e) {
    e.preventDefault();
    const offerId = $(this).data('offer-id');
    const dealType = $(this).data('deal-type');
    const cpuTeam = $(this).data('cpu-team');
    
    // Show modal and load deal details
    $('#dealConfirmationModal').modal('show');
    $('#dealConfirmationModalLabel').text(`Confirm ${dealType === 'sell' ? 'Sale' : 'Purchase'} with ${cpuTeam}`);
    
    // Load deal details via AJAX
    $.ajax({
        url: `/offer/${offerId}/details`,
        method: 'GET',
        success: function(resp) {
            currentDealConfirmation = resp;
            renderDealConfirmation(resp, dealType, cpuTeam);
        },
        error: function() {
            $('#dealConfirmationContent').html('<div class="alert alert-danger">Error loading deal details.</div>');
        }
    });
});

function renderDealConfirmation(deal, dealType, cpuTeam) {
    let html = '<div class="deal-summary">';
    html += '<h6>Deal Summary:</h6>';
    
    if (dealType === 'sell') {
        html += `<div class="row">
            <div class="col-md-6">
                <h6>You Receive:</h6>
                <ul>`;
        if (deal.offered_money > 0) {
            html += `<li>€${deal.offered_money.toLocaleString()}</li>`;
        }
        if (deal.offered_players && deal.offered_players.length > 0) {
            deal.offered_players.forEach(player => {
                html += `<li>${player.player_name} (${player.registered_position})</li>`;
            });
        }
        html += `</ul></div>
            <div class="col-md-6">
                <h6>You Give:</h6>
                <ul>`;
        if (deal.requested_players && deal.requested_players.length > 0) {
            deal.requested_players.forEach(player => {
                html += `<li>${player.player_name} (${player.registered_position})</li>`;
            });
        }
        html += `</ul></div></div>`;
    } else {
        html += `<div class="row">
            <div class="col-md-6">
                <h6>You Receive:</h6>
                <ul>`;
        if (deal.offered_players && deal.offered_players.length > 0) {
            deal.offered_players.forEach(player => {
                html += `<li>${player.player_name} (${player.registered_position})</li>`;
            });
        }
        html += `</ul></div>
            <div class="col-md-6">
                <h6>You Give:</h6>
                <ul>`;
        if (deal.requested_money > 0) {
            html += `<li>€${deal.requested_money.toLocaleString()}</li>`;
        }
        if (deal.requested_players && deal.requested_players.length > 0) {
            deal.requested_players.forEach(player => {
                html += `<li>${player.player_name} (${player.registered_position})</li>`;
            });
        }
        html += `</ul></div></div>`;
    }
    
    html += '</div>';
    $('#dealConfirmationContent').html(html);
}

// Handle deal execution
$('#executeDealBtn').on('click', function() {
    if (!currentDealConfirmation) return;
    
    const offerId = currentDealConfirmation.offer_id;
    const dealType = currentDealConfirmation.deal_type;
    
    // Disable button and show loading
    $(this).prop('disabled', true).text('Executing...');
    
    // Execute the deal
    const url = dealType === 'sell' ? `/offer/${offerId}/confirm_sell` : `/offer/${offerId}/confirm_buy`;
    
    $.ajax({
        url: url,
        method: 'POST',
        dataType: 'json',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        success: function(resp) {
            if (resp.success) {
                // Update budget if element exists
                if (resp.updated_budget !== undefined && $("#user-budget").length) {
                    $("#user-budget").text(resp.updated_budget.toLocaleString('en-US'));
                }
                
                // Show success message
                $('#dealConfirmationContent').html(`
                    <div class="alert alert-success">
                        <h6>Deal Executed Successfully!</h6>
                        <p>${resp.message}</p>
                        <div class="mt-3">
                            <strong>Assets Swapped:</strong>
                            <ul class="mt-2">
                                ${resp.asset_changes ? resp.asset_changes.map(change => `<li>${change}</li>`).join('') : ''}
                            </ul>
                        </div>
                    </div>
                `);
                
                // Update the offer row in the table
                const $row = $(`.confirm-deal-btn[data-offer-id="${offerId}"]`).closest('tr');
                $row.find('td:eq(2)').text('Accepted');
                $row.find('td:eq(3)').html('<span class="badge badge-success">Completed</span>');
                
                // Close modal after delay
                setTimeout(function() {
                    $('#dealConfirmationModal').modal('hide');
                    location.reload(); // Refresh to show updated team/players
                }, 3000);
                
            } else {
                $('#dealConfirmationContent').html(`<div class="alert alert-danger">${resp.error || 'Error executing deal.'}</div>`);
                $('#executeDealBtn').prop('disabled', false).text('Execute Deal');
            }
        },
        error: function(xhr) {
            let errorMsg = 'Error executing deal.';
            if (xhr.responseJSON && xhr.responseJSON.error) {
                errorMsg = xhr.responseJSON.error;
            }
            $('#dealConfirmationContent').html(`<div class="alert alert-danger">${errorMsg}</div>`);
            $('#executeDealBtn').prop('disabled', false).text('Execute Deal');
        }
    });
});

// Handle regular offer acceptance
$(document).on('click', '.accept-offer-btn', function(e) {
    e.preventDefault();
    const offerId = $(this).data('offer-id');
    const $row = $(this).closest('tr');
    
    // Disable button and show loading
    $(this).prop('disabled', true).text('Accepting...');
    
    $.ajax({
        url: `/offer/${offerId}/accept`,
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
                $row.find('td:eq(3)').html('<span class="badge badge-success">Accepted</span>');
            } else {
                alert(resp.error || 'Error accepting offer.');
                $('.accept-offer-btn[data-offer-id="' + offerId + '"]').prop('disabled', false).text('Accept');
            }
        },
        error: function(xhr) {
            let msg = 'Error accepting offer.';
            if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
            alert(msg);
            $('.accept-offer-btn[data-offer-id="' + offerId + '"]').prop('disabled', false).text('Accept');
        }
    });
});

// Handle offer rejection
$(document).on('click', '.reject-offer-btn', function(e) {
    e.preventDefault();
    const offerId = $(this).data('offer-id');
    const $row = $(this).closest('tr');
    
    if (!confirm('Are you sure you want to reject this offer?')) return;
    
    // Disable button and show loading
    $(this).prop('disabled', true).text('Rejecting...');
    
    $.ajax({
        url: `/offer/${offerId}/reject`,
        method: 'POST',
        dataType: 'json',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        success: function(resp) {
            if (resp.success) {
                // Update offer row/status
                $row.find('td:eq(2)').text('Rejected');
                $row.find('td:eq(3)').html('<span class="badge badge-danger">Rejected</span>');
            } else {
                alert(resp.error || 'Error rejecting offer.');
                $('.reject-offer-btn[data-offer-id="' + offerId + '"]').prop('disabled', false).text('Reject');
            }
        },
        error: function(xhr) {
            let msg = 'Error rejecting offer.';
            if (xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
            alert(msg);
            $('.reject-offer-btn[data-offer-id="' + offerId + '"]').prop('disabled', false).text('Reject');
        }
    });
});

// Reset modal state when closed
$('#dealConfirmationModal').on('hidden.bs.modal', function () {
    currentDealConfirmation = null;
    $('#executeDealBtn').prop('disabled', false).text('Execute Deal');
    $('#dealConfirmationContent').html(`
        <div class="text-center">
            <div class="spinner-border" role="status">
                <span class="sr-only">Loading...</span>
            </div>
            <p class="mt-2">Processing deal...</p>
        </div>
    `);
});

// --- Sell Player Modal Logic ---
let sellPlayerId = null;
let sellPlayerName = null;
let sellProposals = [];
let currentSellProposal = null;
let currentSellOfferId = null;

// Add a confirmation modal for sell-to-CPU
if ($('#sellConfirmModal').length === 0) {
    $('body').append(`
    <div class="modal fade" id="sellConfirmModal" tabindex="-1" role="dialog" aria-labelledby="sellConfirmModalLabel" aria-hidden="true">
      <div class="modal-dialog" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title" id="sellConfirmModalLabel">Confirm Negotiation</h5>
            <button type="button" class="close" data-dismiss="modal" aria-label="Close">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body" id="sellConfirmModalBody">
            <!-- Content will be set dynamically -->
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-success" id="confirmSellDealBtn">Confirm</button>
          </div>
        </div>
      </div>
    </div>
    `);
}

$(document).on('click', '.sell-player-btn', function() {
    sellPlayerId = $(this).data('player-id');
    sellPlayerName = $(this).data('player-name');
    sellProposals = [];
    $('#sellPlayerModalLabel').text('Sell Proposals for (' + sellPlayerName + ')');
    $('#sellNegotiationContent').html('<div class="text-center text-muted">Loading proposals...</div>');
    $('#sellPlayerModal').modal('show');
    // Fetch batch of proposals
    $.ajax({
        url: `/sell_player/${sellPlayerId}`,
        method: 'POST',
        contentType: 'application/json',
        success: function(resp) {
            if (resp.success && resp.proposals && resp.proposals.length > 0) {
                sellProposals = resp.proposals;
                renderSellProposals(sellProposals, sellPlayerName);
            } else {
                $('#sellNegotiationContent').html('<div class="text-danger">No proposals received. Try again later.</div>');
            }
        },
        error: function(xhr) {
            if (xhr.status === 403) {
                $('#sellNegotiationContent').html('<div class="alert alert-warning">This player is no longer available for sale negotiations.</div>');
            } else {
                $('#sellNegotiationContent').html('<div class="text-danger">Error loading proposals. Please try again.</div>');
            }
        }
    });
});

function renderSellProposals(proposals, playerName) {
    let html = `<div><strong>Proposals for: ${playerName}</strong></div>`;
    html += '<div class="list-group">';
    proposals.forEach(function(proposal, idx) {
        html += `<div class="list-group-item" id="sell-proposal-${proposal.proposal_id}">
            <div><strong>From:</strong> ${proposal.cpu_team}</div>
            <div><strong>Cash:</strong> €${proposal.cash.toLocaleString()}</div>`;
        if (proposal.player_swap) {
            html += `<div><strong>Player Swap:</strong> ${proposal.player_swap.NAME} (MV: €${proposal.player_swap['Market Value'].toLocaleString()})</div>`;
        }
        html += `<div class="mt-2">
            <button class="btn btn-success btn-sm mr-2 accept-sell-proposal" data-proposal-id="${proposal.proposal_id}">Accept</button>
            <button class="btn btn-warning btn-sm mr-2 negotiate-sell-proposal" data-proposal-id="${proposal.proposal_id}">Negotiate</button>
            <button class="btn btn-danger btn-sm reject-sell-proposal" data-proposal-id="${proposal.proposal_id}">Reject</button>
        </div>
        </div>`;
    });
    html += '</div>';
    $('#sellNegotiationContent').html(html);
}

$(document).on('click', '.accept-sell-proposal', function() {
    const proposalId = $(this).data('proposal-id');
    const proposal = sellProposals.find(p => p.proposal_id === proposalId);
    if (!proposal) return;
    currentSellProposal = proposal;
    // Show confirmation modal
    let confirmHtml = `<div>Are you sure you want to accept this proposal?</div>`;
    confirmHtml += `<div><strong>From:</strong> ${proposal.cpu_team}</div>`;
    confirmHtml += `<div><strong>Cash:</strong> €${proposal.cash.toLocaleString()}</div>`;
    if (proposal.player_swap) {
        confirmHtml += `<div><strong>Player Swap:</strong> ${proposal.player_swap.NAME} (MV: €${proposal.player_swap['Market Value'].toLocaleString()})</div>`;
    }
    $('#sellConfirmModalBody').html(confirmHtml);
    $('#sellConfirmModal').modal('show');
});

$(document).on('click', '#confirmSellDealBtn', function() {
    if (!currentSellProposal) return;
    $('#sellConfirmModalBody').html('<div class="text-center text-muted">Finalizing deal...</div>');
    $('#confirmSellDealBtn').prop('disabled', true);
    $.ajax({
        url: `/sell_player/${sellPlayerId}/accept`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ proposal: currentSellProposal }),
        success: function(resp) {
            if (resp.success) {
                $('#sellConfirmModalBody').html('<div class="alert alert-success">' + resp.message + '</div>');
                setTimeout(function() {
                    $('#sellConfirmModal').modal('hide');
                    location.reload();
                }, 1200);
            } else {
                $('#sellConfirmModalBody').html('<div class="alert alert-danger">' + (resp.error || 'Unknown error') + '</div>');
            }
        },
        error: function() {
            $('#sellConfirmModalBody').html('<div class="alert alert-danger">Error completing deal. Please try again.</div>');
        },
        complete: function() {
            $('#confirmSellDealBtn').prop('disabled', false);
        }
    });
});

$(document).on('click', '.reject-sell-proposal', function() {
    const proposalId = $(this).data('proposal-id');
    $('#sell-proposal-' + proposalId).html('<div class="alert alert-warning">Proposal rejected.</div>');
});

$(document).on('click', '.negotiate-sell-proposal', function() {
    const proposalId = $(this).data('proposal-id');
    const proposal = sellProposals.find(p => p.proposal_id === proposalId);
    if (!proposal) return;
    const $proposalDiv = $('#sell-proposal-' + proposalId);
    $proposalDiv.html('<div class="text-center text-muted">Negotiating with ' + proposal.cpu_team + '...</div>');
    $.ajax({
        url: `/sell_player/${sellPlayerId}/counter`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ proposal: proposal }),
        success: function(resp) {
            if (resp.quit) {
                $proposalDiv.html('<div class="alert alert-warning">' + resp.message + '</div>');
            } else if (resp.proposal) {
                // Update the proposal in sellProposals and re-render just this proposal
                const idx = sellProposals.findIndex(p => p.proposal_id === proposalId);
                if (idx !== -1) sellProposals[idx] = resp.proposal;
                let html = `<div><strong>From:</strong> ${resp.proposal.cpu_team}</div>`;
                html += `<div><strong>Cash:</strong> €${resp.proposal.cash.toLocaleString()}</div>`;
                if (resp.proposal.player_swap) {
                    html += `<div><strong>Player Swap:</strong> ${resp.proposal.player_swap.NAME} (MV: €${resp.proposal.player_swap['Market Value'].toLocaleString()})</div>`;
                }
                html += `<div class="mt-2">
                    <button class="btn btn-success btn-sm mr-2 accept-sell-proposal" data-proposal-id="${resp.proposal.proposal_id}">Accept</button>
                    <button class="btn btn-warning btn-sm mr-2 negotiate-sell-proposal" data-proposal-id="${resp.proposal.proposal_id}">Negotiate</button>
                    <button class="btn btn-danger btn-sm reject-sell-proposal" data-proposal-id="${resp.proposal.proposal_id}">Reject</button>
                </div>`;
                $proposalDiv.html(html);
            } else {
                $proposalDiv.html('<div class="alert alert-danger">Negotiation failed. Try again.</div>');
            }
        },
        error: function() {
            $proposalDiv.html('<div class="alert alert-danger">Error negotiating with club.</div>');
        }
    });
});
