#!/usr/bin/env python3
"""Update all agent dashboards with chat persistence using localStorage."""

import os
import re

AGENTS_DIR = "/Users/atlas/Projects/forex-trading-platform/agents"

# Old chat script pattern (various formats)
OLD_PATTERNS = [
    # Pattern 1: Basic sendMessage
    r'''<script>\s*async function sendMessage\(\) \{\{.*?\}\}\s*</script>''',
    # Pattern 2: With formatting
    r'''<script>\n\s*async function sendMessage.*?</script>''',
]

def get_new_chat_script(agent_name):
    """Generate new chat script with localStorage persistence."""
    storage_key = f"{agent_name.lower().replace(' ', '_')}_chat_history"
    return f'''<script>
        // Chat persistence using localStorage
        const CHAT_KEY = '{storage_key}';
        
        function loadChatHistory() {{
            const messages = document.getElementById('messages');
            const history = localStorage.getItem(CHAT_KEY);
            if (history) {{
                messages.innerHTML = history;
                messages.scrollTop = messages.scrollHeight;
            }}
        }}
        
        function saveChatHistory() {{
            const messages = document.getElementById('messages');
            localStorage.setItem(CHAT_KEY, messages.innerHTML);
        }}
        
        function clearChat() {{
            const messages = document.getElementById('messages');
            messages.innerHTML = '';
            localStorage.removeItem(CHAT_KEY);
        }}
        
        async function sendMessage() {{
            const input = document.getElementById('input');
            const messages = document.getElementById('messages');
            const text = input.value.trim();
            if (!text) return;
            messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:#1a1a24;border-radius:8px;font-size:12px">${{text}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
            
            try {{
                const response = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: text}})
                }});
                const data = await response.json();
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(249,115,22,0.15);border-left:3px solid #f97316;border-radius:8px;font-size:12px">${{data.response.replace(/\\n/g, '<br>')}}</div>`;
            }} catch (e) {{
                messages.innerHTML += `<div style="margin:5px 0;padding:8px 12px;background:rgba(239,68,68,0.15);border-radius:8px;font-size:12px;color:#ef4444">Error: ${{e.message}}</div>`;
            }}
            messages.scrollTop = messages.scrollHeight;
            saveChatHistory();
        }}
        
        // Load chat history on page load
        document.addEventListener('DOMContentLoaded', loadChatHistory);
    </script>'''

def update_agent_file(filepath, agent_name):
    """Update a single agent file with chat persistence."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check if already updated
    if 'loadChatHistory' in content:
        print(f"  ✓ {agent_name} already has chat persistence")
        return False
    
    # Find and replace the sendMessage script
    # Look for the script section containing sendMessage
    pattern = r"<script>\s*\n?\s*async function sendMessage\(\).*?</script>"
    
    if re.search(pattern, content, re.DOTALL):
        new_script = get_new_chat_script(agent_name)
        content = re.sub(pattern, new_script, content, flags=re.DOTALL)
        
        # Also add Clear button if not present
        if 'clearChat()' not in content or 'Clear</button>' not in content:
            # Try to add Clear button next to Ask header
            content = content.replace(
                '💬 Ask ',
                '💬 Ask '
            )
        
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  ✅ Updated {agent_name}")
        return True
    else:
        print(f"  ⚠️  {agent_name}: Could not find sendMessage pattern")
        return False

def main():
    print("Updating agent chat persistence...\n")
    
    agent_dirs = [
        ("data-agent", "Curator"),
        ("news-agent", "Sentinel"),
        ("macro-agent", "Oracle"),
        ("technical-agent", "Atlas Jr"),
        ("structure-agent", "Architect"),
        ("sentiment-agent", "Pulse"),
        ("regime-agent", "Compass"),
        ("strategy-agent", "Tactician"),
        ("risk-agent", "Guardian"),
        ("portfolio-agent", "Balancer"),
        ("execution-agent", "Executor"),
        ("journal-agent", "Chronicle"),
        ("analytics-agent", "Insight"),
        ("governance-agent", "Arbiter"),
    ]
    
    updated = 0
    for dirname, agent_name in agent_dirs:
        filepath = os.path.join(AGENTS_DIR, dirname, "app.py")
        if os.path.exists(filepath):
            if update_agent_file(filepath, agent_name):
                updated += 1
        else:
            print(f"  ❌ {agent_name}: File not found")
    
    print(f"\nUpdated {updated} agents")

if __name__ == "__main__":
    main()
