const PALETTE = ['#4f46e5', '#0891b2', '#059669', '#d97706', '#dc2626', '#7c3aed', '#db2777', '#0d9488', '#ea580c'];

function createBarChart(canvasId, labels, data, label) {
    // crea un objeto de tipo bar chart
    new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                backgroundColor: PALETTE,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {display: false}},
            scales: {y: {beginAtZero: true, title: {display: true, text: 'ms'}}}
        }
    });
}

function createLineChart(canvasId, labels, data, label, color) {
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);

    new Chart(document.getElementById(canvasId), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                borderColor: color,
                backgroundColor: `rgba(${r},${g},${b},0.1)`,
                fill: true,
                tension: 0.3,
                pointRadius: 4,
            }]
        },
        options: {
            responsive: true,
            scales: {y: {beginAtZero: false, title: {display: true, text: 'ms'}}}
        }
    });
}
