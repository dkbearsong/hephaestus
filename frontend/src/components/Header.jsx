import React, { useState, useEffect, useRef } from 'react';
import { Bell, Search, Terminal, Flame, CheckCircle2, AlertCircle, X } from 'lucide-react';
import NotificationPopup from './NotificationPopup';
import { api } from '../services/api';

export default function Header({
  notificationData,
  onRefreshNotifications,
  onSelectTicket,
  onSelectWorkLog
}) {
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const popupRef = useRef(null);

  // Close popup if clicked outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (popupRef.current && !popupRef.current.contains(event.target)) {
        setIsPopupOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Handle Full-Text Search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await api.searchFullText(searchQuery);
        setSearchResults(res);
        setIsSearchOpen(true);
      } catch (e) {
        console.error('Search failed:', e);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const { icon_status, needs_input_count, completed_count, notifications = [] } = notificationData || {};

  const handleRespond = async (id, action) => {
    try {
      await api.respondNotification(id, action);
      onRefreshNotifications();
    } catch (e) {
      console.error('Failed to respond to notification:', e);
    }
  };

  return (
    <header className="h-14 bg-slate-900/90 border-b border-slate-800 backdrop-blur px-4 flex items-center justify-between z-30 shrink-0 sticky top-0">
      {/* Brand Title */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shadow-lg shadow-orange-500/20 text-white">
          <Flame className="w-5 h-5 fill-current" />
        </div>
        <div>
          <span className="font-bold tracking-tight text-slate-100 text-sm md:text-base flex items-center gap-2">
            Hephaestus
            <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-orange-950/80 text-orange-400 border border-orange-800/60">
              Coding Harness
            </span>
          </span>
        </div>
      </div>

      {/* Center Search Bar */}
      <div className="relative flex-1 max-w-md mx-6">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Full-text search logs, diffs, chats (tsvector)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setIsSearchOpen(true)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500/50"
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('');
                setSearchResults(null);
                setIsSearchOpen(false);
              }}
              className="absolute right-2.5 top-2.5 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Search Results Dropdown */}
        {isSearchOpen && searchResults && (
          <div className="absolute top-10 left-0 right-0 max-h-96 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-y-auto z-50 p-2">
            <div className="text-[11px] font-semibold text-slate-400 px-3 py-1 border-b border-slate-800 flex justify-between items-center">
              <span>Search Results ({searchResults.total_matches})</span>
              <button
                onClick={() => setIsSearchOpen(false)}
                className="text-slate-500 hover:text-slate-300"
              >
                Close
              </button>
            </div>

            {searchResults.total_matches === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500">
                No matching results for "{searchQuery}"
              </div>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {searchResults.work_logs?.map((item) => (
                  <div
                    key={`log-${item.id}`}
                    onClick={() => {
                      onSelectWorkLog(item.id);
                      setIsSearchOpen(false);
                    }}
                    className="p-2.5 hover:bg-slate-800/70 rounded cursor-pointer transition"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        {item.jira_key}
                      </span>
                      <span
                        className="text-[11px] font-medium"
                        style={{ color: item.project_color || '#38bdf8' }}
                      >
                        {item.project_name}
                      </span>
                      <span className="text-[10px] text-slate-500 ml-auto">
                        Rank {parseFloat(item.rank).toFixed(2)}
                      </span>
                    </div>
                    <div
                      className="text-xs text-slate-300 line-clamp-2"
                      dangerouslySetInnerHTML={{ __html: item.headline || item.summary_changes }}
                    />
                  </div>
                ))}

                {searchResults.chat_messages?.map((item) => (
                  <div
                    key={`chat-${item.id}`}
                    onClick={() => {
                      onSelectTicket(item.ticket_id);
                      setIsSearchOpen(false);
                    }}
                    className="p-2.5 hover:bg-slate-800/70 rounded cursor-pointer transition"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        {item.jira_key} [Chat]
                      </span>
                      <span className="text-[11px] text-slate-400 capitalize">{item.sender}</span>
                    </div>
                    <div
                      className="text-xs text-slate-300 line-clamp-2"
                      dangerouslySetInnerHTML={{ __html: item.headline || item.content }}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right Side: Agent Notifications Link with Dynamic Icon */}
      <div className="relative" ref={popupRef}>
        <button
          onClick={() => setIsPopupOpen(!isPopupOpen)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all ${
            icon_status === 'red'
              ? 'bg-rose-950/70 border-rose-600 text-rose-200 hover:bg-rose-900/80 shadow-lg shadow-rose-950/50'
              : icon_status === 'yellow'
              ? 'bg-amber-950/60 border-amber-600/80 text-amber-200 hover:bg-amber-900/80'
              : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-slate-100'
          }`}
        >
          {/* Shaking Red Bell when waiting on user input, Yellow when completed */}
          <div className="relative">
            <Bell
              className={`w-4 h-4 ${
                icon_status === 'red'
                  ? 'text-rose-400 animate-periodic-shake'
                  : icon_status === 'yellow'
                  ? 'text-amber-400'
                  : 'text-slate-400'
              }`}
            />
            {needs_input_count > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-2.5 h-2.5 bg-rose-500 rounded-full animate-ping" />
            )}
          </div>

          <span>Agent Notifications</span>

          {needs_input_count > 0 ? (
            <span className="px-1.5 py-0.2 text-[10px] font-bold rounded-full bg-rose-600 text-white">
              {needs_input_count}
            </span>
          ) : completed_count > 0 ? (
            <span className="px-1.5 py-0.2 text-[10px] font-bold rounded-full bg-amber-600 text-white">
              {completed_count}
            </span>
          ) : null}
        </button>

        {/* Notification Popup Dropdown */}
        <NotificationPopup
          isOpen={isPopupOpen}
          notifications={notifications}
          onClose={() => setIsPopupOpen(false)}
          onSelectTicket={onSelectTicket}
          onRespond={handleRespond}
        />
      </div>
    </header>
  );
}
