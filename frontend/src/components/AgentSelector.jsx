import { useState, useEffect, useRef } from 'react';
import './AgentSelector.css';

export default function AgentSelector({ availableAgents, selectedAgents, onSelectionChange, chairmanModel, onChairmanChange }) {
  const [isOpen, setIsOpen] = useState(false);
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
    // Convert "openai/gpt-5.1" to "GPT 5.1"
    const parts = modelId.split('/');
    if (parts.length > 1) {
      const name = parts[1];
      // Capitalize first letter and handle common patterns
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
            {availableAgents.map((agent) => (
              <label key={agent} className="agent-item">
                <input
                  type="checkbox"
                  checked={selectedAgents.includes(agent)}
                  onChange={() => handleAgentToggle(agent)}
                />
                <span className="agent-name">{getDisplayName(agent)}</span>
                <span className="agent-id">{agent}</span>
              </label>
            ))}
          </div>

          <div className="chairman-selector">
            <label className="chairman-label">Chairman Model:</label>
            <select
              value={chairmanModel}
              onChange={(e) => onChairmanChange(e.target.value)}
              className="chairman-select"
            >
              {availableAgents.map((agent) => (
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
