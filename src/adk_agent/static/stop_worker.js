
// [New Feature] Stop Specific Worker
window.stopWorker = async function (workerPort, workerSessionId) {
    if (!confirm(`Confirm to force stop Worker-${workerPort}?`)) return;

    const btn = document.querySelector(`#swarm-card-msg-${workerPort} .stop-worker-btn`); // This selector might need adjustment based on how I generate ID
    // Actually, let's just use the button instance if possible, or visually indicate loading

    console.log(`[Stop Worker] Port: ${workerPort}, Session: ${workerSessionId}`);

    try {
        const response = await fetch('/api/stop_worker', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                worker_port: workerPort,
                worker_session_id: workerSessionId,
                app_name: APP_NAME,
                user_id: getUserId()
            })
        });

        const res = await response.json();
        if (res.status === 'success') {
            alert(`Worker-${workerPort} stopped successfully.`);
            // Update UI to show stopped? 
            // The worker should eventually send a 'fail' or we can manually mark it.
            // But let's verify via the event stream.
        } else {
            alert(`Failed to stop worker: ${res.error || res.message}`);
        }
    } catch (e) {
        console.error("Stop worker error:", e);
        alert("Error stopping worker.");
    }
}
