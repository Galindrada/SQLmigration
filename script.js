// Team data with logos and names
const teams = {
    'barcelona': { name: 'FC Barcelona', logo: '🔵🔴', colors: 'team-colors-barcelona' },
    'real-madrid': { name: 'Real Madrid', logo: '👑⚪', colors: 'team-colors-real-madrid' },
    'manchester-united': { name: 'Manchester United', logo: '👹🔴', colors: 'team-colors-manchester-united' },
    'manchester-city': { name: 'Manchester City', logo: '💙⚪', colors: 'team-colors-manchester-city' },
    'liverpool': { name: 'Liverpool', logo: '🔴🐦', colors: 'team-colors-liverpool' },
    'chelsea': { name: 'Chelsea', logo: '🔵🦁', colors: 'team-colors-chelsea' },
    'arsenal': { name: 'Arsenal', logo: '🔴🔫', colors: 'team-colors-arsenal' },
    'tottenham': { name: 'Tottenham', logo: '⚪🐓', colors: 'team-colors-tottenham' },
    'juventus': { name: 'Juventus', logo: '⚫⚪', colors: 'team-colors-juventus' },
    'ac-milan': { name: 'AC Milan', logo: '🔴⚫', colors: 'team-colors-ac-milan' },
    'inter-milan': { name: 'Inter Milan', logo: '🔵⚫', colors: 'team-colors-inter-milan' },
    'bayern-munich': { name: 'Bayern Munich', logo: '🔴⚪', colors: 'team-colors-bayern-munich' },
    'borussia-dortmund': { name: 'Borussia Dortmund', logo: '💛⚫', colors: 'team-colors-borussia-dortmund' },
    'psg': { name: 'Paris Saint-Germain', logo: '🔵🔴', colors: 'team-colors-psg' },
    'atletico-madrid': { name: 'Atlético Madrid', logo: '🔴⚪', colors: 'team-colors-atletico-madrid' }
};

function updateTeamLogo(side) {
    const teamSelect = document.getElementById(side + 'Team');
    const logoElement = document.getElementById(side + 'Logo');
    const nameElement = document.getElementById(side + 'TeamName');
    
    const selectedTeam = teamSelect.value;
    
    if (selectedTeam && teams[selectedTeam]) {
        logoElement.innerHTML = `<span class="logo-placeholder">${teams[selectedTeam].logo}</span>`;
        nameElement.textContent = teams[selectedTeam].name;
    } else {
        logoElement.innerHTML = `<span class="logo-placeholder">${side === 'home' ? '🏠' : '✈️'}</span>`;
        nameElement.textContent = side === 'home' ? 'Home' : 'Away';
    }
}

function generateOverlay() {
    // Get form values
    const homeTeam = document.getElementById('homeTeam').value;
    const awayTeam = document.getElementById('awayTeam').value;
    const homeScore = document.getElementById('homeScore').value;
    const awayScore = document.getElementById('awayScore').value;
    const homeScorers = document.getElementById('homeScorers').value;
    const awayScorers = document.getElementById('awayScorers').value;
    const competition = document.getElementById('competition').value;
    const matchday = document.getElementById('matchday').value;
    const matchDate = document.getElementById('matchDate').value;
    const overlayStyle = document.getElementById('overlayStyle').value;
    
    // Update overlay
    const overlay = document.getElementById('overlay');
    overlay.className = `overlay ${overlayStyle}`;
    
    // Update competition info
    document.querySelector('.competition-name').textContent = competition || 'Competition';
    document.querySelector('.matchday').textContent = matchday || '';
    
    // Update match date
    if (matchDate) {
        const date = new Date(matchDate);
        document.getElementById('matchDateDisplay').textContent = date.toLocaleDateString('en-US', {
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });
    }
    
    // Update scores
    document.getElementById('homeScoreDisplay').textContent = homeScore || '-';
    document.getElementById('awayScoreDisplay').textContent = awayScore || '-';
    
    // Update team logos and names
    updateTeamLogo('home');
    updateTeamLogo('away');
    
    // Update goal scorers
    updateScorers('home', homeScorers);
    updateScorers('away', awayScorers);
    
    // Apply team colors if available
    applyTeamColors(homeTeam, awayTeam);
}

function updateScorers(side, scorersText) {
    const scorersDisplay = document.getElementById(side + 'ScorersDisplay');
    
    if (scorersText.trim()) {
        const scorers = scorersText.trim().split('\n');
        scorersDisplay.innerHTML = scorers.map(scorer => 
            `<div class="scorer">⚽ ${scorer.trim()}</div>`
        ).join('');
    } else {
        scorersDisplay.innerHTML = '<div class="scorer">No goals</div>';
    }
}

function applyTeamColors(homeTeam, awayTeam) {
    const overlay = document.getElementById('overlay');
    
    // Remove existing team color classes
    overlay.classList.remove(...Object.values(teams).map(team => team.colors));
    
    // Apply color based on home team (you can customize this logic)
    if (homeTeam && teams[homeTeam]) {
        // For now, keep the default gradient, but you can uncomment below to use team colors
        // overlay.classList.add(teams[homeTeam].colors);
    }
}

function downloadOverlay() {
    const overlay = document.getElementById('overlay');
    
    // Use html2canvas to convert the overlay to an image
    html2canvas(overlay, {
        backgroundColor: null,
        scale: 2,
        width: 800,
        height: overlay.offsetHeight,
        useCORS: true
    }).then(canvas => {
        // Create download link
        const link = document.createElement('a');
        link.download = 'football-overlay.png';
        link.href = canvas.toDataURL();
        link.click();
    }).catch(error => {
        console.error('Error generating image:', error);
        alert('Error generating image. Please try again or check your browser settings.');
    });
}

function clearForm() {
    // Clear all form inputs
    document.getElementById('homeTeam').value = '';
    document.getElementById('awayTeam').value = '';
    document.getElementById('homeScore').value = '';
    document.getElementById('awayScore').value = '';
    document.getElementById('homeScorers').value = '';
    document.getElementById('awayScorers').value = '';
    document.getElementById('competition').value = '';
    document.getElementById('matchday').value = '';
    document.getElementById('matchDate').value = '';
    document.getElementById('overlayStyle').value = 'modern';
    
    // Reset overlay to default state
    const overlay = document.getElementById('overlay');
    overlay.className = 'overlay modern';
    
    document.querySelector('.competition-name').textContent = 'Select teams and competition';
    document.querySelector('.matchday').textContent = '';
    document.getElementById('matchDateDisplay').textContent = '';
    document.getElementById('homeScoreDisplay').textContent = '-';
    document.getElementById('awayScoreDisplay').textContent = '-';
    document.getElementById('homeLogo').innerHTML = '<span class="logo-placeholder">🏠</span>';
    document.getElementById('awayLogo').innerHTML = '<span class="logo-placeholder">✈️</span>';
    document.getElementById('homeTeamName').textContent = 'Home';
    document.getElementById('awayTeamName').textContent = 'Away';
    document.getElementById('homeScorersDisplay').innerHTML = '';
    document.getElementById('awayScorersDisplay').innerHTML = '';
}

// Add event listeners for real-time updates
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to all form inputs for real-time preview
    const inputs = ['homeTeam', 'awayTeam', 'homeScore', 'awayScore', 'homeScorers', 'awayScorers', 'competition', 'matchday', 'matchDate', 'overlayStyle'];
    
    inputs.forEach(inputId => {
        const element = document.getElementById(inputId);
        if (element) {
            element.addEventListener('input', generateOverlay);
            element.addEventListener('change', generateOverlay);
        }
    });
    
    // Initial generation
    generateOverlay();
});

// Add html2canvas library dynamically
function loadHtml2Canvas() {
    if (typeof html2canvas === 'undefined') {
        const script = document.createElement('script');
        script.src = 'https://html2canvas.hertzen.com/dist/html2canvas.min.js';
        script.onload = function() {
            console.log('html2canvas loaded successfully');
        };
        script.onerror = function() {
            console.error('Failed to load html2canvas');
            alert('Failed to load image generation library. Please check your internet connection.');
        };
        document.head.appendChild(script);
    }
}

// Load html2canvas when page loads
document.addEventListener('DOMContentLoaded', loadHtml2Canvas);