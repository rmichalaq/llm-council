import { useState, useEffect, useRef } from 'react';
import './AgentSelector.css';

export default function AgentSelector({ availableAgents, selectedAgents, onSelectionChange, chairmanModel, onChairmanChange, modelsData }) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const dropdownRef = useRef(null);
  const toggleRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        isOpen &&
        dropdownRef.current &&
        toggleRef.current &&
        !dropdownRef.current.contains(event.target) &&
        !toggleRef.current.contains(event.target)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleAgentToggle = (agent) => {
    const newSelection = selectedAgents.includes(agent)
      ? selectedAgents.filter(a => a !== agent)
      : [...selectedAgents, agent];
    onSelectionChange(newSelection);
  };

  const handleSelectAll = () => {
    onSelectionChange([...availableAgents]);
  };

  const handleDeselectAll = () => {
    onSelectionChange([]);
  };

  const getDisplayName = (modelId) => {
    const modelInfo = modelsData?.find(m => m.id === modelId);
    if (modelInfo?.name) {
      return modelInfo.name;
    }
    // Fallback: Convert "openai/gpt-5.1" to "GPT 5.1"
    const parts = modelId.split('/');
    if (parts.length > 1) {
      const name = parts[1];
      return name
        .replace(/^gpt-/, 'GPT ')
        .replace(/^gemini-/, 'Gemini ')
        .replace(/^claude-/, 'Claude ')
        .replace(/^grok-/, 'Grok ')
        .replace(/-/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase());
    }
    return modelId;
  };

  // Categorize models by their strengths
  const getModelStrength = (modelId, modelInfo) => {
    const idLower = modelId.toLowerCase();
    const nameLower = (modelInfo?.name || '').toLowerCase();
    const descLower = (modelInfo?.description || '').toLowerCase();
    const combined = `${idLower} ${nameLower} ${descLower}`;

    // Reasoning models
    if (combined.includes('reasoning') || 
        combined.includes('o1') || 
        combined.includes('deepseek-r') ||
        combined.includes('qwen-reasoning') ||
        combined.includes('deepseek-reasoner')) {
      return 'reasoning';
    }

    // Coding models
    if (combined.includes('code') || 
        combined.includes('coder') ||
        combined.includes('codellama') ||
        combined.includes('deepseek-coder') ||
        combined.includes('wizardcoder') ||
        combined.includes('starcoder') ||
        combined.includes('codegen')) {
      return 'coding';
    }

    // Default to general
    return 'general';
  };

  // Filter agents based on search
  const filteredAgents = availableAgents.filter(agent => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    const modelInfo = modelsData?.find(m => m.id === agent);
    return agent.toLowerCase().includes(query) || 
           modelInfo?.name?.toLowerCase().includes(query) ||
           modelInfo?.description?.toLowerCase().includes(query);
  });

  // Sort alphabetically by display name
  const sortedAgents = [...filteredAgents].sort((a, b) => {
    const nameA = getDisplayName(a).toLowerCase();
    const nameB = getDisplayName(b).toLowerCase();
    return nameA.localeCompare(nameB);
  });

  // Group by strength
  const groupedAgents = sortedAgents.reduce((groups, agent) => {
    const modelInfo = modelsData?.find(m => m.id === agent);
    const strength = getModelStrength(agent, modelInfo);
    if (!groups[strength]) {
      groups[strength] = [];
    }
    groups[strength].push(agent);
    return groups;
  }, {});

  // Define strength order and labels
  const strengthOrder = ['reasoning', 'coding', 'general'];
  const strengthLabels = {
    reasoning: '🧠 Reasoning',
    coding: '💻 Coding',
    general: '🌟 General Purpose'
  };
  return (
    <div className="agent-selector">
      <button
        ref={toggleRef}
        className="agent-selector-toggle"
        onClick={() => setIsOpen(!isOpen)}
        title="Select agents"
      >
        <span className="agent-icon">🤖</span>
        <span className="agent-count">{selectedAgents.length} agent{selectedAgents.length !== 1 ? 's' : ''}</span>
        <span className="dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div ref={dropdownRef} className="agent-selector-dropdown">
          <div className="agent-selector-header">
            <h3>Select Council Members</h3>
            <div className="selector-actions">
              <button onClick={handleSelectAll} className="action-link">Select All</button>
              <button onClick={handleDeselectAll} className="action-link">Deselect All</button>
            </div>
          </div>

          <div className="agent-list">
            <input
              type="text"
              placeholder="Search models..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="agent-search-input"
            />
            {sortedAgents.length === 0 ? (
              <div className="no-results">No models found matching "{searchQuery}"</div>
            ) : (
              strengthOrder.map(strength => {
                const agentsInGroup = groupedAgents[strength] || [];
                if (agentsInGroup.length === 0) return null;
                
                return (
                  <div key={strength} className="strength-group">
                    <div className="strength-group-header">{strengthLabels[strength]}</div>
                    {agentsInGroup.map((agent) => {
                      const modelInfo = modelsData?.find(m => m.id === agent);
                      return (
                        <label key={agent} className="agent-item">
                          <input
                            type="checkbox"
                            checked={selectedAgents.includes(agent)}
                            onChange={() => handleAgentToggle(agent)}
                          />
                          <div className="agent-info">
                            <div className="agent-name">{getDisplayName(agent)}</div>
                            <div className="agent-id">{agent}</div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>

          <div className="chairman-selector">
            <label className="chairman-label">Chairman Model:</label>
            <select
              value={chairmanModel}
              onChange={(e) => onChairmanChange(e.target.value)}
              className="chairman-select"
            >
              {sortedAgents.map((agent) => (
                <option key={agent} value={agent}>
                  {getDisplayName(agent)}
                </option>
              ))}
            </select>
          </div>

          {selectedAgents.length === 0 && (
            <div className="agent-warning">
              ⚠️ Please select at least one agent
            </div>
          )}
        </div>
      )}
    </div>
  );
}
