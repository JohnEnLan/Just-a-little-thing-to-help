document.addEventListener("DOMContentLoaded", () => {
    const overviewRoot = document.getElementById("dashboard-electricity-overview");
    const chartElement = document.getElementById("dashboard-electricity-chart");
    const statusLine = document.getElementById("dashboard-electricity-status");

    if (!overviewRoot || !chartElement || !statusLine) {
        return;
    }

    const apiUrl = overviewRoot.dataset.apiUrl;
    const chartLibraryAvailable = typeof echarts !== "undefined";
    const chart = chartLibraryAvailable ? echarts.init(chartElement) : null;
    const palette = ["#215c3c", "#b37a14", "#c9483c"];

    function setStatus(message, tone = "muted") {
        statusLine.textContent = message;
        statusLine.dataset.tone = tone;
    }

    function renderChartMessage(message, tone = "muted") {
        if (chart) {
            chart.setOption({
                graphic: {
                    type: "text",
                    left: "center",
                    top: "middle",
                    style: {
                        text: message,
                        fill: tone === "error" ? "#c9483c" : "#5d7464",
                        fontSize: 14,
                    },
                },
                xAxis: { show: false },
                yAxis: { show: false },
                series: [],
            });
            return;
        }

        chartElement.innerHTML = `<div class="chart-fallback" data-tone="${tone}">${message}</div>`;
    }

    function createChartOption(buildings) {
        return {
            backgroundColor: "transparent",
            animationDuration: 400,
            color: palette,
            legend: {
                data: buildings.map((building) => building.name),
                top: 10,
                right: 18,
                textStyle: {
                    color: "#5d7464",
                },
            },
            grid: {
                left: 70,
                right: 28,
                top: 56,
                bottom: 56,
            },
            tooltip: {
                trigger: "axis",
                confine: true,
                backgroundColor: "rgba(23, 48, 31, 0.92)",
                borderWidth: 0,
                textStyle: {
                    color: "#f7fbf5",
                },
                valueFormatter: (value) => `${Number(value || 0).toFixed(2)} kWh`,
            },
            xAxis: {
                type: "time",
                axisLine: {
                    lineStyle: {
                        color: "rgba(22, 55, 33, 0.18)",
                    },
                },
                axisLabel: {
                    color: "#5d7464",
                },
                splitLine: {
                    show: false,
                },
            },
            yAxis: {
                type: "value",
                name: "kWh",
                nameLocation: "middle",
                nameGap: 50,
                nameTextStyle: {
                    color: "#5d7464",
                },
                axisLabel: {
                    color: "#5d7464",
                },
                splitLine: {
                    lineStyle: {
                        color: "rgba(22, 55, 33, 0.08)",
                    },
                },
            },
            series: buildings.flatMap((building, index) => {
                const color = palette[index % palette.length];

                return [
                    {
                        name: building.name,
                        type: "line",
                        smooth: true,
                        showSymbol: false,
                        lineStyle: {
                            width: 3,
                            color,
                        },
                        itemStyle: {
                            color,
                        },
                        emphasis: {
                            focus: "series",
                        },
                        data: building.readings.map((reading) => [
                            reading.timestamp,
                            Number(reading.electricity_kwh || 0),
                        ]),
                    },
                    {
                        name: `${building.name} anomalies`,
                        type: "scatter",
                        symbolSize: 12,
                        z: 6,
                        itemStyle: {
                            color,
                            borderColor: "#ffffff",
                            borderWidth: 2,
                            shadowBlur: 10,
                            shadowColor: "rgba(22, 55, 33, 0.18)",
                        },
                        emphasis: {
                            focus: "series",
                            scale: 1.15,
                        },
                        data: (building.anomalies || []).map((anomaly) => [
                            anomaly.timestamp,
                            Number(anomaly.electricity_kwh || 0),
                        ]),
                        tooltip: {
                            valueFormatter: (value) =>
                                `${Number(value || 0).toFixed(2)} kWh anomaly`,
                        },
                    },
                ];
            }),
        };
    }

    async function loadChart() {
        if (!apiUrl) {
            renderChartMessage("Comparison chart is unavailable.", "error");
            setStatus("Comparison chart is unavailable.", "error");
            return;
        }

        setStatus("Loading three-building electricity comparison...");

        try {
            const response = await fetch(apiUrl, {
                headers: {
                    Accept: "application/json",
                },
            });

            if (!response.ok) {
                throw new Error(`Request failed with status ${response.status}`);
            }

            const payload = await response.json();
            const buildings = (payload.buildings || []).filter(
                (building) => Array.isArray(building.readings) && building.readings.length
            );

            if (!buildings.length) {
                renderChartMessage("No electricity readings are available yet.");
                setStatus("No electricity readings are available yet.");
                return;
            }

            if (!chart) {
                renderChartMessage(
                    "Chart unavailable because ECharts did not load.",
                    "warning"
                );
                setStatus(
                    `Loaded ${buildings.length} buildings, but the chart library is unavailable.`,
                    "warning"
                );
                return;
            }

            chart.setOption(createChartOption(buildings));

            const pointCount = Math.max(
                ...buildings.map((building) => building.readings.length)
            );
            const anomalyCount = buildings.reduce(
                (total, building) => total + (building.anomalies || []).length,
                0
            );
            setStatus(
                `Loaded ${buildings.length} buildings, up to ${pointCount} hourly readings per line, and ${anomalyCount} anomaly markers.`,
                "success"
            );
        } catch (error) {
            renderChartMessage("Failed to load electricity comparison.", "error");
            setStatus(`Failed to load electricity comparison: ${error.message}`, "error");
        }
    }

    if (chart) {
        window.addEventListener("resize", () => {
            chart.resize();
        });
    }

    loadChart();
});
