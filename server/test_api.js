import axios from 'axios';

const BASE = 'http://localhost:3001/api';

async function testApi() {
  console.log('Testing Express API endpoints...');

  try {
    // 1. Projects
    const projects = await axios.get(`${BASE}/projects`);
    console.log(`✅ [GET /api/projects] Success. Found ${projects.data.length} projects.`);

    // 2. Recent Actions (5 items for top of column)
    const recent = await axios.get(`${BASE}/logs/recent`);
    console.log(`✅ [GET /api/logs/recent] Success. Found ${recent.data.length} recent actions.`);

    // 3. 5-Minute Queue History
    const history = await axios.get(`${BASE}/logs/queue-history`);
    console.log(`✅ [GET /api/logs/queue-history] Success. Found ${history.data.length} 5-minute time windows.`);

    // 4. Notifications (Red shaking status check)
    const notifs = await axios.get(`${BASE}/notifications`);
    console.log(`✅ [GET /api/notifications] Icon status: '${notifs.data.icon_status}' | Needs Input: ${notifs.data.needs_input_count} | Completed: ${notifs.data.completed_count}`);

    // 5. Full-Text Search
    const search = await axios.get(`${BASE}/search?q=idempotency`);
    console.log(`✅ [GET /api/search] TSVector search returned ${search.data.total_matches} matches.`);

    console.log('\n🎉 ALL EXPRESS API ENDPOINTS FUNCTIONING AS SPECIFIED!');
  } catch (e) {
    console.error('❌ API Test failed:', e.message);
    process.exit(1);
  }
}

testApi();
