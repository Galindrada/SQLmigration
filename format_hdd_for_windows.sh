#!/bin/bash
# Script to format HDD with NTFS filesystem for Windows 10 compatibility
# WARNING: This will DESTROY all data on the specified drive

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}HDD Windows 10 Compatibility Formatter${NC}"
echo "========================================="

# Show available drives
echo -e "\n${YELLOW}Available drives:${NC}"
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS

echo -e "\n${RED}WARNING: This script will completely erase the selected drive!${NC}"
echo -e "${RED}Make sure you have backed up any important data.${NC}"

# Get drive selection from user
echo -e "\n${YELLOW}Please enter the drive to format (e.g., sdb, sdc):${NC}"
read -p "Drive: /dev/" DRIVE

# Validate drive exists
if [ ! -b "/dev/$DRIVE" ]; then
    echo -e "${RED}Error: Drive /dev/$DRIVE does not exist!${NC}"
    exit 1
fi

# Confirm selection
echo -e "\n${RED}You selected: /dev/$DRIVE${NC}"
echo -e "${RED}This will PERMANENTLY DELETE all data on this drive!${NC}"
read -p "Type 'YES' to continue: " CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    echo -e "${YELLOW}Operation cancelled.${NC}"
    exit 0
fi

echo -e "\n${YELLOW}Starting drive preparation...${NC}"

# Unmount any mounted partitions
echo "Unmounting any mounted partitions..."
sudo umount /dev/${DRIVE}* 2>/dev/null || true

# Create new partition table (GPT for modern systems)
echo "Creating new GPT partition table..."
sudo parted /dev/$DRIVE --script mklabel gpt

# Create a single NTFS partition using the entire disk
echo "Creating NTFS partition..."
sudo parted /dev/$DRIVE --script mkpart primary ntfs 0% 100%

# Wait a moment for the system to recognize the new partition
sleep 2

# Format the partition with NTFS
echo "Formatting with NTFS filesystem..."
sudo mkfs.ntfs -f -L "Windows_Drive" /dev/${DRIVE}1

# Set the partition as bootable (optional, useful for external drives)
echo "Setting partition flags..."
sudo parted /dev/$DRIVE --script set 1 msftdata on

echo -e "\n${GREEN}Drive formatting completed successfully!${NC}"
echo -e "${GREEN}Drive /dev/$DRIVE is now formatted with NTFS and ready for Windows 10.${NC}"

# Show final result
echo -e "\n${YELLOW}Final drive information:${NC}"
lsblk -f /dev/$DRIVE

echo -e "\n${YELLOW}To mount this drive in Linux later, use:${NC}"
echo "sudo mkdir /mnt/windows_drive"
echo "sudo mount /dev/${DRIVE}1 /mnt/windows_drive"

echo -e "\n${YELLOW}To auto-mount on boot, add this line to /etc/fstab:${NC}"
echo "/dev/${DRIVE}1 /mnt/windows_drive ntfs defaults,uid=1000,gid=1000,umask=022 0 0"