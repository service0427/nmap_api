import { state } from './state.js';
import { updateCriticalAlertMonitor, filterDevicesLocally } from './devices.js';
import { filterLteCards } from './lte.js';
import { filterDestinationsLocally } from './destinations.js';

// Fetch API Data
export async function fetchData(manual = false) {
  state.isFetching = true;
  
  // Rotate refresh icon if manual refresh
  const refreshIcon = document.getElementById("refresh-icon");
  if (manual && refreshIcon) {
    refreshIcon.classList.add("spinning");
  }
  
  try {
    const res = await fetch("/api/v1/admin/summary");
    if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
    const data = await res.json();
    
    updateUI(data);
  } catch (err) {
    console.error("Fetch Data Error:", err);
  } finally {
    state.isFetching = false;
    if (refreshIcon) {
      refreshIcon.classList.remove("spinning");
    }
  }
}

// Update UI elements based on API payload
export function updateUI(data) {
  // 1. Statistics Progress Cards
  const stats = data.summary;
  state.totalTodaySuccess = stats.total_today_success || 0;
  state.totalYesterdaySuccess = stats.total_yesterday_success || 0;
  state.pastDateStrs = stats.past_date_strs || [];
  
  // FSD
  const fsdPct = stats.fsd_target > 0 ? Math.round((stats.fsd_success / stats.fsd_target) * 100) : 0;
  const fsdPctEl = document.getElementById("fsd-percent");
  const fsdProgressFill = document.getElementById("fsd-progress-fill");
  const fsdCounts = document.getElementById("fsd-counts");
  if (fsdPctEl) fsdPctEl.innerText = `${fsdPct}%`;
  if (fsdProgressFill) fsdProgressFill.style.width = `${Math.min(100, fsdPct)}%`;
  if (fsdCounts) fsdCounts.innerText = `목표: ${stats.fsd_target} | 성공: ${stats.fsd_success} | 실패: ${stats.fsd_fail}`;

  // LUF
  const lufPct = stats.luf_target > 0 ? Math.round((stats.luf_success / stats.luf_target) * 100) : 0;
  const lufPctEl = document.getElementById("luf-percent");
  const lufProgressFill = document.getElementById("luf-progress-fill");
  const lufCounts = document.getElementById("luf-counts");
  if (lufPctEl) lufPctEl.innerText = `${lufPct}%`;
  if (lufProgressFill) lufProgressFill.style.width = `${Math.min(100, lufPct)}%`;
  if (lufCounts) lufCounts.innerText = `목표: ${stats.luf_target} | 성공: ${stats.luf_success} | 실패: ${stats.luf_fail}`;

  // TEST
  const testPct = stats.test_target > 0 ? Math.round((stats.test_success / stats.test_target) * 100) : 0;
  const testPctEl = document.getElementById("test-percent");
  const testProgressFill = document.getElementById("test-progress-fill");
  const testCounts = document.getElementById("test-counts");
  if (testPctEl) testPctEl.innerText = `${testPct}%`;
  if (testProgressFill) testProgressFill.style.width = `${Math.min(100, testPct)}%`;
  if (testCounts) testCounts.innerText = `목표: ${stats.test_target} | 성공: ${stats.test_success} | 실패: ${stats.test_fail}`;

  // ssolup
  const ssolupPct = stats.ssolup_target > 0 ? Math.round((stats.ssolup_success / stats.ssolup_target) * 100) : 0;
  const ssolupPctEl = document.getElementById("ssolup-percent");
  const ssolupProgressFill = document.getElementById("ssolup-progress-fill");
  const ssolupCounts = document.getElementById("ssolup-counts");
  if (ssolupPctEl) ssolupPctEl.innerText = `${ssolupPct}%`;
  if (ssolupProgressFill) ssolupProgressFill.style.width = `${Math.min(100, ssolupPct)}%`;
  if (ssolupCounts) ssolupCounts.innerText = `목표: ${stats.ssolup_target} | 성공: ${stats.ssolup_success} | 실패: ${stats.ssolup_fail}`;

  // ghost
  const ghostPct = stats.ghost_target > 0 ? Math.round((stats.ghost_success / stats.ghost_target) * 100) : 0;
  const ghostPctEl = document.getElementById("ghost-percent");
  const ghostProgressFill = document.getElementById("ghost-progress-fill");
  const ghostCounts = document.getElementById("ghost-counts");
  if (ghostPctEl) ghostPctEl.innerText = `${ghostPct}%`;
  if (ghostProgressFill) ghostProgressFill.style.width = `${Math.min(100, ghostPct)}%`;
  if (ghostCounts) ghostCounts.innerText = `목표: ${stats.ghost_target} | 성공: ${stats.ghost_success} | 실패: ${stats.ghost_fail}`;

  // rudolph
  const rudolphPct = stats.rudolph_target > 0 ? Math.round((stats.rudolph_success / stats.rudolph_target) * 100) : 0;
  const rudolphPctEl = document.getElementById("rudolph-percent");
  const rudolphProgressFill = document.getElementById("rudolph-progress-fill");
  const rudolphCounts = document.getElementById("rudolph-counts");
  if (rudolphPctEl) rudolphPctEl.innerText = `${rudolphPct}%`;
  if (rudolphProgressFill) rudolphProgressFill.style.width = `${Math.min(100, rudolphPct)}%`;
  if (rudolphCounts) rudolphCounts.innerText = `목표: ${stats.rudolph_target} | 성공: ${stats.rudolph_success} | 실패: ${stats.rudolph_fail}`;

  // Total Unified
  const totalPct = stats.total_target > 0 ? Math.round((stats.success / stats.total_target) * 100) : 0;
  const totalPctEl = document.getElementById("total-percent");
  const totalProgressFill = document.getElementById("total-progress-fill");
  const totalCounts = document.getElementById("total-counts");
  if (totalPctEl) totalPctEl.innerText = `${totalPct}%`;
  if (totalProgressFill) totalProgressFill.style.width = `${Math.min(100, totalPct)}%`;
  if (totalCounts) totalCounts.innerText = `성공: ${stats.success} / 전체 목표: ${stats.total_target} (남음: ${stats.remain})`;

  // 2. System Health Info
  const sys = data.system;
  const sysCpu = document.getElementById("sys-cpu");
  const sysRam = document.getElementById("sys-ram");
  const sysDisk = document.getElementById("sys-disk");
  if (sysCpu) sysCpu.innerText = sys.cpu;
  if (sysRam) sysRam.innerText = `${sys.ram_mb} MB`;
  if (sysDisk) sysDisk.innerText = `${sys.disk_free_gb} GB`;

  // 3. LTE Quick info on dashboard
  const lteQuick = document.getElementById("lte-quick-list");
  if (lteQuick) {
    lteQuick.innerHTML = "";
    if (data.lte && data.lte.length > 0) {
      data.lte.slice(0, 4).forEach(l => {
        const upUsedBytes = (l.today_now_up || 0) - (l.today_init_up || 0);
        const dnUsedBytes = (l.today_now_dn || 0) - (l.today_init_dn || 0);
        const totalMB = Math.max(0, (upUsedBytes + dnUsedBytes) / (1024 * 1024)).toFixed(1);
        
        const div = document.createElement("div");
        div.innerHTML = `
          <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.2rem;">
            <span style="font-weight: 600;">${l.modem_name}</span>
            <span style="color: var(--color-primary); font-weight: bold;">${totalMB} MB</span>
          </div>
          <div class="progress-bar" style="height: 5px;">
            <div class="progress-fill primary" style="width: ${Math.min(100, (totalMB / 10))}%;"></div>
          </div>
        `;
        lteQuick.appendChild(div);
      });
    } else {
      lteQuick.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 0.8rem;">오늘 데이터 사용량 집계가 없습니다.</div>`;
    }
  }

  // 4. Timeline successes feed
  const feed = document.getElementById("success-feed-container");
  if (feed) {
    feed.innerHTML = `
      <div class="panel-header" style="border-bottom: 1px solid var(--border-color); padding: 0.75rem 0.25rem;">
        <h3 class="panel-title"><i data-lucide="check-circle-2" style="width:16px; height:16px; color: var(--color-primary);"></i>실시간 작업 성공 피드</h3>
      </div>
    `;
    const feedItemsDiv = document.createElement("div");
    feedItemsDiv.className = "timeline";
    if (data.success_feed && data.success_feed.length > 0) {
      data.success_feed.forEach(f => {
        const item = document.createElement("div");
        item.className = "timeline-item";
        const timeFormatted = f.start_time ? f.start_time.substring(11, 19) : "--:--:--";
        
        item.innerHTML = `
          <div class="timeline-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </div>
          <div class="timeline-content">
            <span class="timeline-title">${f.dest_name}</span>
            <span class="timeline-meta">${f.device_memo} | ${timeFormatted}</span>
          </div>
        `;
        feedItemsDiv.appendChild(item);
      });
    } else {
      feedItemsDiv.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 2rem; font-size: 0.8rem;">최근 성공 이력이 없습니다.</div>`;
    }
    feed.appendChild(feedItemsDiv);
  }

  // 5. Store devices globally to support group accordion filtering
  state.rawDevices = data.devices || [];
  const countBadge = document.getElementById("total-devices-count-badge");
  if (countBadge) countBadge.innerText = `${state.rawDevices.length}대 등록됨`;
  
  // Calculate 20m Critical Alerts & Populate banner
  updateCriticalAlertMonitor(data.alarms);
  
  // Render Device group list
  filterDevicesLocally();

  // 6. Bind data to LTE Cards
  state.rawLteData = data.lte || [];
  filterLteCards();

  // 7. Bind logs
  if (state.logsGridApi) state.logsGridApi.setGridOption('rowData', data.logs || []);
  
  // Store destinations globally for manual input filtering
  state.rawDestinations = data.destinations || [];
  filterDestinationsLocally();
  
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

// Action: Toggle Device Mute
export async function toggleMute(deviceId, isMuted) {
  try {
    const res = await fetch("/api/v1/admin/device/toggle_mute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, is_muted: isMuted })
    });
    if (!res.ok) throw new Error("Toggle Mute fail");
    fetchData();
  } catch (err) {
    alert("알람 상태 변경 실패: " + err.message);
  }
}

// Action: Update Dest Limit
export async function updateDestLimit(destId, newLimit) {
  try {
    const res = await fetch("/api/v1/admin/dest/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dest_id: destId, limit: parseInt(newLimit, 10) })
    });
    if (!res.ok) throw new Error("Update limit failed");
    
    // Update local memory data instantly to avoid grid redraw lag
    if (state.rawDestinations) {
      const targetObj = state.rawDestinations.find(x => x.dest_id === destId);
      if (targetObj) targetObj.target = parseInt(newLimit, 10);
    }
  } catch (err) {
    alert("한도값 변경 실패: " + err.message);
    fetchData();
  }
}

// Action: Update Dest Status
export async function updateDestStatus(destId, newStatus) {
  try {
    const res = await fetch("/api/v1/admin/dest/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dest_id: destId, status: newStatus })
    });
    if (!res.ok) throw new Error("Update status failed");
    fetchData();
  } catch (err) {
    alert("목적지 활성 상태 변경 실패: " + err.message);
  }
}

// Bind to window for HTML click handlers
window.fetchData = fetchData;
window.toggleMute = toggleMute;
window.updateDestLimit = updateDestLimit;
window.updateDestStatus = updateDestStatus;
