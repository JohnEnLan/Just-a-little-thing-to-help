document.addEventListener("DOMContentLoaded", () => {
    const analyticsRoot = document.getElementById("building-analytics");
    if (!analyticsRoot) {
        return;
    }

    const buildingId = analyticsRoot.dataset.buildingId;
    const buildingName = analyticsRoot.dataset.buildingName || "Building";
    const statusLine = document.getElementById("detection-status");
    const tableBody = document.getElementById("anomaly-table-body");
    const anomalyCountLabel = document.getElementById("anomaly-count-label");
    const energyCaption = document.getElementById("chart-energy-caption");
    const chartLibraryAvailable = typeof echarts !== "undefined";

    const chartStates = {
        energy48: createChartState("chart-energy-48", "Electricity - Last 48 Hours"),
        carbon48: createChartState("chart-carbon-48", "Estimated CO2e - Last 48 Hours"),
        cost48: createChartState("chart-cost-48", "Estimated Cost - Last 48 Hours"),
        overview7d: createChartState("chart-overview-7d", "Electricity and CO2e - Last 7 Days"),
    };

    let readings = [];
    let anomalies = [];

    function createChartState(elementId, title) {
        const element = document.getElementById(elementId);
        return {
            element,
            title,
            chart: chartLibraryAvailable && element ? echarts.init(element) : null,
        };
    }

    function setStatus(message, tone = "muted") {
        statusLine.textContent = message;
        statusLine.dataset.tone = tone;
    }

    async function fetchJSON(url, options = {}) {
        const response = await fetch(url, {
            headers: {
                Accept: "application/json",
            },
            ...options,
        });

        if (!response.ok) {
            const payload = await response.text();
            throw new Error(payload || `Request failed with status ${response.status}`);
        }

        return response.json();
    }

    function renderChartMessage(state, message, tone = "muted") {
        if (!state.element) {
            return;
        }

        if (state.chart) {
            state.chart.setOption({
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

        state.element.innerHTML = `<div class="chart-fallback" data-tone="${tone}">${message}</div>`;
    }

    function formatNumber(value, digits = 2) {
        return Number(value || 0).toFixed(digits);
    }

    function formatHourLabel(timestamp, includeDate = false) {
        const date = new Date(timestamp);
        if (Number.isNaN(date.getTime())) {
            return timestamp;
        }

        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        const hour = String(date.getHours()).padStart(2, "0");

        return includeDate ? `${month}-${day} ${hour}:00` : `${hour}:00`;
    }

    function roundTo(value, digits = 2) {
        const factor = 10 ** digits;
        return Math.round(value * factor) / factor;
    }

    function getAxisPrecision(step) {
        if (!Number.isFinite(step) || step <= 0) {
            return 2;
        }

        if (step >= 10) {
            return 0;
        }

        if (step >= 1) {
            return 1;
        }

        return 2;
    }

    function formatAxisValue(value, precision) {
        const rounded = roundTo(Number(value || 0), precision);
        if (precision === 0) {
            return String(Math.round(rounded));
        }
        return rounded.toFixed(precision);
    }

    function getConfinedTooltipPosition(point, _params, _dom, _rect, size) {
        const [mouseX, mouseY] = point;
        const [viewWidth, viewHeight] = size.viewSize;
        const [contentWidth, contentHeight] = size.contentSize;
        const padding = 14;

        const x = Math.min(
            Math.max(mouseX - contentWidth - 18, padding),
            viewWidth - contentWidth - padding
        );
        const y = Math.min(
            Math.max(mouseY - contentHeight - 18, padding),
            viewHeight - contentHeight - padding
        );

        return [x, y];
    }

    function getRecentReadings(hours) {
        return readings.slice(-hours);
    }

    function getWindowReadings(hours) {
        const latestWindow = getRecentReadings(hours);
        if (!latestWindow.length || !anomalies.length) {
            if (energyCaption) {
                energyCaption.textContent = "48-hour electricity profile with anomaly markers.";
            }
            return latestWindow;
        }

        const latestWindowStart = latestWindow[0].timestamp;
        const anomaliesInLatestWindow = anomalies.filter(
            (anomaly) => anomaly.timestamp >= latestWindowStart
        );
        if (anomaliesInLatestWindow.length) {
            if (energyCaption) {
                energyCaption.textContent =
                    "Latest 48-hour electricity profile with anomaly markers.";
            }
            return latestWindow;
        }

        const latestAnomalyTimestamp = anomalies[anomalies.length - 1].timestamp;
        const anomalyIndex = readings.findIndex(
            (reading) => reading.timestamp === latestAnomalyTimestamp
        );
        if (anomalyIndex === -1) {
            if (energyCaption) {
                energyCaption.textContent = "48-hour electricity profile with anomaly markers.";
            }
            return latestWindow;
        }

        const endIndexExclusive = Math.min(readings.length, anomalyIndex + 25);
        const startIndex = Math.max(0, endIndexExclusive - hours);

        if (energyCaption) {
            energyCaption.textContent =
                "48-hour electricity profile centred on the most recent detected anomaly.";
        }

        return readings.slice(startIndex, endIndexExclusive);
    }

    function getAnomaliesInWindow(windowReadings) {
        if (!windowReadings.length) {
            return [];
        }

        const startTimestamp = windowReadings[0].timestamp;
        const endTimestamp = windowReadings[windowReadings.length - 1].timestamp;

        return anomalies.filter(
            (anomaly) => anomaly.timestamp >= startTimestamp && anomaly.timestamp <= endTimestamp
        );
    }

    function getRecentWindowByHours(hours) {
        return readings.slice(-hours);
    }

    function createAxisExtent(minValue, maxValue, lowerPaddingRatio, upperPaddingRatio) {
        if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
            return { min: 0, max: 1 };
        }

        if (minValue === maxValue) {
            const padding = minValue === 0 ? 1 : Math.abs(minValue) * 0.2;
            return {
                min: Math.max(0, minValue - padding),
                max: maxValue + padding,
            };
        }

        const span = maxValue - minValue;
        return {
            min: Math.max(0, minValue - span * lowerPaddingRatio),
            max: maxValue + span * upperPaddingRatio,
        };
    }

    function getNiceStep(rawStep) {
        if (!Number.isFinite(rawStep) || rawStep <= 0) {
            return 1;
        }

        const exponent = 10 ** Math.floor(Math.log10(rawStep));
        const fraction = rawStep / exponent;

        if (fraction <= 1) {
            return exponent;
        }
        if (fraction <= 2) {
            return 2 * exponent;
        }
        if (fraction <= 2.5) {
            return 2.5 * exponent;
        }
        if (fraction <= 5) {
            return 5 * exponent;
        }
        return 10 * exponent;
    }

    function createAxisScale(values, lowerPaddingRatio, upperPaddingRatio, segmentCount = 5) {
        const extent = createAxisExtent(
            Math.min(...values),
            Math.max(...values),
            lowerPaddingRatio,
            upperPaddingRatio
        );
        const rawInterval = Math.max((extent.max - extent.min) / segmentCount, 0.01);
        let interval = getNiceStep(rawInterval);
        let min = Math.max(0, Math.floor(extent.min / interval) * interval);
        let max = min + interval * segmentCount;

        while (max < extent.max) {
            interval = getNiceStep(interval * 1.1);
            min = Math.max(0, Math.floor(extent.min / interval) * interval);
            max = min + interval * segmentCount;
        }

        if (min > extent.min) {
            min = Math.max(0, min - interval);
            max = min + interval * segmentCount;
        }

        const precision = getAxisPrecision(interval);

        return {
            min: roundTo(min, precision + 2),
            max: roundTo(max, precision + 2),
            interval: roundTo(interval, precision + 2),
            precision,
        };
    }

    function formatOverviewTooltip(params) {
        if (!params.length) {
            return "";
        }

        const timestamp = params[0].axisValue;
        const seriesOrder = ["Electricity", "Estimated CO2e", "Electricity anomaly", "CO2e anomaly"];
        const unitMap = {
            Electricity: "kWh",
            "Estimated CO2e": "kg CO2e",
            "Electricity anomaly": "kWh anomaly",
            "CO2e anomaly": "kg CO2e anomaly",
        };

        const lines = [`<strong>${formatHourLabel(timestamp, true)}</strong>`];

        seriesOrder.forEach((seriesName) => {
            const entry = params.find((param) => param.seriesName === seriesName);
            if (!entry) {
                return;
            }

            const value = Array.isArray(entry.value) ? entry.value[1] : entry.value;
            lines.push(
                `${entry.marker}${seriesName}: ${formatNumber(value, 2)} ${unitMap[seriesName]}`
            );
        });

        return lines.join("<br/>");
    }

    function createTimeSeriesOption({
        yAxisName,
        color,
        areaColor,
        seriesName,
        seriesKey,
        data,
        anomalyData = [],
    }) {
        return {
            backgroundColor: "transparent",
            grid: {
                left: 62,
                right: 22,
                top: 22,
                bottom: 42,
            },
            tooltip: {
                trigger: "axis",
                confine: true,
                position: getConfinedTooltipPosition,
                backgroundColor: "rgba(23, 48, 31, 0.92)",
                borderWidth: 0,
                textStyle: {
                    color: "#f7fbf5",
                },
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
                name: yAxisName,
                nameLocation: "middle",
                nameGap: 44,
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
            series: [
                {
                    name: seriesName,
                    type: "line",
                    smooth: true,
                    showSymbol: false,
                    lineStyle: {
                        width: 3,
                        color,
                    },
                    areaStyle: {
                        color: areaColor,
                    },
                    data: data.map((reading) => [reading.timestamp, reading[seriesKey]]),
                },
                ...(anomalyData.length
                    ? [
                          {
                              name: "Anomaly",
                              type: "scatter",
                              symbolSize: 11,
                              itemStyle: {
                                  color: "#c9483c",
                              },
                              data: anomalyData.map((anomaly) => [
                                  anomaly.timestamp,
                                  anomaly[seriesKey],
                              ]),
                          },
                      ]
                    : []),
            ],
        };
    }

    function createOverviewOption(windowReadings, windowAnomalies) {
        const categories = windowReadings.map((entry) => entry.timestamp);
        const categoryInterval = Math.max(0, Math.floor(categories.length / 7) - 1);
        const indexByTimestamp = new Map(
            categories.map((timestamp, index) => [timestamp, index])
        );
        const electricityValues = windowReadings.map((entry) => Number(entry.electricity_kwh || 0));
        const carbonValues = windowReadings.map((entry) => Number(entry.estimated_co2_kg || 0));
        const electricityScale = createAxisScale(
            electricityValues,
            0.12,
            0.18
        );
        const carbonScale = createAxisScale(
            carbonValues,
            0.46,
            0.72
        );

        return {
            backgroundColor: "transparent",
            animationDuration: 400,
            grid: {
                left: 76,
                right: 88,
                top: 62,
                bottom: 58,
                containLabel: false,
            },
            tooltip: {
                trigger: "axis",
                confine: true,
                position: getConfinedTooltipPosition,
                formatter: formatOverviewTooltip,
                axisPointer: {
                    type: "line",
                    snap: true,
                    lineStyle: {
                        color: "rgba(33, 92, 60, 0.24)",
                        width: 1.5,
                    },
                },
                backgroundColor: "rgba(23, 48, 31, 0.92)",
                borderWidth: 0,
                textStyle: {
                    color: "#f7fbf5",
                },
            },
            legend: {
                top: 10,
                right: 18,
                textStyle: {
                    color: "#5d7464",
                },
            },
            xAxis: {
                type: "category",
                data: categories,
                boundaryGap: false,
                axisLabel: {
                    color: "#5d7464",
                    interval: categoryInterval,
                    hideOverlap: false,
                    formatter: (value) => formatHourLabel(value, true),
                },
                axisTick: {
                    alignWithLabel: true,
                    lineStyle: {
                        color: "rgba(22, 55, 33, 0.18)",
                    },
                },
                axisLine: {
                    lineStyle: {
                        color: "rgba(22, 55, 33, 0.18)",
                    },
                },
                splitLine: {
                    show: false,
                },
            },
            yAxis: [
                {
                    type: "value",
                    name: "kWh",
                    min: electricityScale.min,
                    max: electricityScale.max,
                    interval: electricityScale.interval,
                    splitNumber: 5,
                    nameLocation: "middle",
                    nameGap: 46,
                    axisLine: {
                        show: true,
                        lineStyle: {
                            color: "#215c3c",
                        },
                    },
                    axisTick: {
                        show: true,
                    },
                    axisLabel: {
                        color: "#215c3c",
                        formatter: (value) => formatAxisValue(value, electricityScale.precision),
                    },
                    nameTextStyle: {
                        color: "#215c3c",
                        fontWeight: 700,
                    },
                    splitLine: {
                        lineStyle: {
                            color: "rgba(22, 55, 33, 0.1)",
                            type: "solid",
                        },
                    },
                },
                {
                    type: "value",
                    name: "kg CO2e",
                    position: "right",
                    min: carbonScale.min,
                    max: carbonScale.max,
                    interval: carbonScale.interval,
                    splitNumber: 5,
                    nameLocation: "middle",
                    nameGap: 46,
                    axisLine: {
                        show: true,
                        lineStyle: {
                            color: "#b37a14",
                        },
                    },
                    axisTick: {
                        show: true,
                    },
                    axisLabel: {
                        color: "#b37a14",
                        formatter: (value) => formatAxisValue(value, carbonScale.precision),
                    },
                    nameTextStyle: {
                        color: "#b37a14",
                        fontWeight: 700,
                    },
                    splitLine: {
                        show: false,
                    },
                },
            ],
            series: [
                {
                    name: "Electricity",
                    type: "line",
                    smooth: false,
                    connectNulls: true,
                    showSymbol: false,
                    yAxisIndex: 0,
                    lineStyle: {
                        width: 3,
                        color: "#215c3c",
                    },
                    itemStyle: {
                        color: "#215c3c",
                    },
                    data: windowReadings.map((entry) => entry.electricity_kwh),
                },
                {
                    name: "Estimated CO2e",
                    type: "line",
                    smooth: false,
                    connectNulls: true,
                    showSymbol: false,
                    yAxisIndex: 1,
                    lineStyle: {
                        width: 3,
                        color: "#b37a14",
                    },
                    itemStyle: {
                        color: "#b37a14",
                    },
                    data: windowReadings.map((entry) => entry.estimated_co2_kg),
                },
                {
                    name: "Electricity anomaly",
                    type: "scatter",
                    yAxisIndex: 0,
                    symbolSize: 12,
                    z: 6,
                    itemStyle: {
                        color: "#c9483c",
                    },
                    data: windowAnomalies
                        .map((anomaly) => {
                            const index = indexByTimestamp.get(anomaly.timestamp);
                            if (index === undefined) {
                                return null;
                            }

                            return [index, anomaly.electricity_kwh];
                        })
                        .filter(Boolean),
                },
                {
                    name: "CO2e anomaly",
                    type: "scatter",
                    yAxisIndex: 1,
                    symbolSize: 12,
                    z: 6,
                    itemStyle: {
                        color: "#7b4f00",
                    },
                    data: windowAnomalies
                        .map((anomaly) => {
                            const index = indexByTimestamp.get(anomaly.timestamp);
                            if (index === undefined) {
                                return null;
                            }

                            return [index, anomaly.estimated_co2_kg];
                        })
                        .filter(Boolean),
                },
            ],
        };
    }

    function renderCharts() {
        const recentReadings = getWindowReadings(48);
        const recentAnomalies = getAnomaliesInWindow(recentReadings);
        const overviewReadings = getRecentWindowByHours(24 * 7);
        const overviewAnomalies = getAnomaliesInWindow(overviewReadings);

        if (!recentReadings.length) {
            renderChartMessage(chartStates.energy48, "No electricity readings available for the last 48 hours.");
            renderChartMessage(chartStates.carbon48, "No carbon estimate available without readings.");
            renderChartMessage(chartStates.cost48, "No cost estimate available without readings.");
        } else {
            const seriesConfigs = [
                {
                    state: chartStates.energy48,
                    yAxisName: "kWh",
                    color: "#215c3c",
                    areaColor: "rgba(33, 92, 60, 0.12)",
                    seriesName: "Electricity (kWh)",
                    seriesKey: "electricity_kwh",
                    anomalyData: recentAnomalies,
                },
                {
                    state: chartStates.carbon48,
                    yAxisName: "kg CO2e",
                    color: "#b37a14",
                    areaColor: "rgba(215, 156, 47, 0.14)",
                    seriesName: "Estimated CO2e (kg)",
                    seriesKey: "estimated_co2_kg",
                    anomalyData: recentAnomalies,
                },
                {
                    state: chartStates.cost48,
                    yAxisName: "GBP",
                    color: "#c9483c",
                    areaColor: "rgba(201, 72, 60, 0.12)",
                    seriesName: "Estimated Cost (GBP)",
                    seriesKey: "estimated_cost_gbp",
                    anomalyData: recentAnomalies,
                },
            ];

            seriesConfigs.forEach((config) => {
                if (!config.state.chart) {
                    renderChartMessage(
                        config.state,
                        "Chart unavailable because ECharts did not load.",
                        "warning"
                    );
                    return;
                }

                config.state.chart.setOption(
                    createTimeSeriesOption({
                        yAxisName: config.yAxisName,
                        color: config.color,
                        areaColor: config.areaColor,
                        seriesName: config.seriesName,
                        seriesKey: config.seriesKey,
                        data: recentReadings,
                        anomalyData: config.anomalyData || [],
                    })
                );
            });
        }

        if (!overviewReadings.length) {
            renderChartMessage(chartStates.overview7d, "No 7-day overview is available yet.");
        } else if (!chartStates.overview7d.chart) {
            renderChartMessage(
                chartStates.overview7d,
                "Chart unavailable because ECharts did not load.",
                "warning"
            );
        } else {
            chartStates.overview7d.chart.setOption(
                createOverviewOption(overviewReadings, overviewAnomalies)
            );
        }
    }

    function renderTable() {
        tableBody.innerHTML = "";

        if (!anomalies.length) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5">No anomalies detected yet. Automatic detection will refresh each hour.</td>
                </tr>
            `;
            anomalyCountLabel.textContent = "0";
            return;
        }

        anomalies.forEach((anomaly) => {
            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${anomaly.timestamp}</td>
                <td>${formatNumber(anomaly.electricity_kwh, 2)}</td>
                <td>${formatNumber(anomaly.estimated_co2_kg, 2)}</td>
                <td>${formatNumber(anomaly.estimated_cost_gbp, 2)}</td>
                <td>${formatNumber(anomaly.anomaly_score, 3)}</td>
            `;
            tableBody.appendChild(row);
        });

        anomalyCountLabel.textContent = String(anomalies.length);
    }

    async function loadData() {
        setStatus("Loading electricity, CO2e, cost, and anomaly history...");

        try {
            const [readingsPayload, anomaliesPayload] = await Promise.all([
                fetchJSON(`/api/buildings/${buildingId}/readings`),
                fetchJSON(`/api/buildings/${buildingId}/anomalies`),
            ]);

            readings = readingsPayload.readings || [];
            anomalies = anomaliesPayload.anomalies || [];

            renderCharts();
            renderTable();

            if (chartLibraryAvailable) {
                setStatus(
                    `Loaded ${readings.length} readings, 48-hour charts, 7-day overview, and ${anomalies.length} anomaly records.`,
                    anomalies.length ? "success" : "muted"
                );
            } else {
                setStatus(
                    `Loaded ${readings.length} readings and ${anomalies.length} anomaly records. Charts are unavailable because ECharts did not load.`,
                    "warning"
                );
            }
        } catch (error) {
            Object.values(chartStates).forEach((state) => {
                renderChartMessage(state, "Failed to load chart data.", "error");
            });
            setStatus(`Failed to load data: ${error.message}`, "error");
        }
    }

    if (chartLibraryAvailable) {
        window.addEventListener("resize", () => {
            Object.values(chartStates).forEach((state) => {
                if (state.chart) {
                    state.chart.resize();
                }
            });
        });
    }

    loadData();
});
