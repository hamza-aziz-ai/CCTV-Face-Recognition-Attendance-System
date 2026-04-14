#!/bin/bash

# Function to find the primary IP for Ethernet or Wi-Fi
get_primary_ip() {
    # Get all active interfaces except loopback
    active_interfaces=$(ip -o link show up | awk -F': ' '{print $2}' | grep -Ev "lo|docker|br-")

    # Debug output for active interfaces
    # echo "Active interfaces: $active_interfaces"

    # Check for Ethernet first (enp*)
    for iface in $active_interfaces; do
        if [[ $iface == eth* || $iface == enp* ]]; then
            ethernet_ip=$(ip addr show "$iface" | grep -E "inet\s" | awk '{print $2}' | cut -d'/' -f1)
            if [[ -n $ethernet_ip ]]; then
                echo "$ethernet_ip"
                return
            fi
        fi
    done

    # Check for Wi-Fi next (wlan* or wlp*)
    for iface in $active_interfaces; do
        if [[ $iface == wlan* || $iface == wlp* ]]; then
            wifi_ip=$(ip addr show "$iface" | grep -E "inet\s" | awk '{print $2}' | cut -d'/' -f1)
            if [[ -n $wifi_ip ]]; then
                echo "$wifi_ip"
                return
            fi
        fi
    done

    # No valid IP found
    echo ""
}

# Get the primary IP address
IP_ADDRESS=$(get_primary_ip)

# echo $IP_ADDRESS

# If no primary IP is found, default to localhost
if [[ -z "$IP_ADDRESS" ]]; then
    IP_ADDRESS="127.0.0.1"
fi

# Use the IP_ADDRESS variable
# echo "The system's IP address is: $IP_ADDRESS"
