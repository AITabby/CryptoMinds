// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * CryptoMinds Skill 质押与罚没合约
 * 
 * 功能：
 * 1. Skill 提交者质押 BNB
 * 2. 平台（多签）可执行罚没
 * 3. 罚没金额退还给受影响的买家
 * 4. 提交者可随时退出并取回质押（无违规时）
 */
contract SkillStaking {
    
    address public owner;           // 平台合约 owner
    address public multiSig;        // 多签地址（用于确认罚没）
    
    struct Stake {
        address seller;             // 质押者钱包
        string skillId;             // Skill 标识
        uint256 amount;             // 质押金额 (wei)
        uint256 stakedAt;           // 质押时间
        bool slashed;               // 是否已被罚没
    }
    
    mapping(string => Stake) public stakes;  // skillId => Stake
    string[] public allSkillIds;
    
    // 事件
    event Staked(address indexed seller, string skillId, uint256 amount);
    event Slashed(string indexed skillId, address indexed buyer, uint256 amount, string reason);
    event Withdrawn(address indexed seller, string skillId, uint256 amount);
    event MultiSigUpdated(address indexed oldMultiSig, address indexed newMultiSig);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }
    
    modifier onlyOwnerOrMultiSig() {
        require(msg.sender == owner || msg.sender == multiSig, "Not owner or multiSig");
        _;
    }
    
    constructor(address _multiSig) {
        owner = msg.sender;
        multiSig = _multiSig;
    }
    
    /**
     * 质押 BNB（提交 Skill 时调用）
     */
    function stake(string memory skillId) external payable {
        require(msg.value > 0, "Must stake > 0");
        require(bytes(stakes[skillId].skillId).length == 0, "Skill already staked");
        
        Stake memory s = Stake({
            seller: msg.sender,
            skillId: skillId,
            amount: msg.value,
            stakedAt: block.timestamp,
            slashed: false
        });
        
        stakes[skillId] = s;
        allSkillIds.push(skillId);
        
        emit Staked(msg.sender, skillId, msg.value);
    }
    
    /**
     * 罚没质押（owner 或 multiSig 任一授权即可执行）
     * @param skillId 被罚没的 Skill ID
     * @param buyer 受影响的买家（罚没金额转入此地址）
     * @param reason 罚没原因
     */
    function slash(
        string memory skillId, 
        address buyer, 
        string memory reason
    ) external onlyOwnerOrMultiSig {
        Stake storage s = stakes[skillId];
        require(bytes(s.skillId).length != 0, "Skill not staked");
        require(!s.slashed, "Already slashed");
        require(s.seller != buyer, "Buyer cannot be seller");
        
        s.slashed = true;
        uint256 amount = s.amount;
        s.amount = 0;
        
        // 转给受影响的买家
        (bool ok, ) = payable(buyer).call{value: amount}("");
        require(ok, "Transfer failed");
        
        emit Slashed(skillId, buyer, amount, reason);
    }
    
    /**
     * 取回质押（无违规时，Skill 提交者自行取回）
     */
    function withdraw(string memory skillId) external {
        Stake storage s = stakes[skillId];
        require(msg.sender == s.seller, "Not the staker");
        require(!s.slashed, "Already slashed");
        require(s.amount > 0, "Nothing to withdraw");
        
        uint256 amount = s.amount;
        s.amount = 0;
        
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "Transfer failed");
        
        emit Withdrawn(msg.sender, skillId, amount);
    }
    
    /**
     * 查询质押信息
     */
    function getStake(string memory skillId) external view returns (
        address seller,
        uint256 amount,
        uint256 stakedAt,
        bool slashed
    ) {
        Stake storage s = stakes[skillId];
        return (s.seller, s.amount, s.stakedAt, s.slashed);
    }
    
    /**
     * 更新多签地址
     */
    function setMultiSig(address _newMultiSig) external onlyOwner {
        require(_newMultiSig != address(0), "Zero address");
        emit MultiSigUpdated(multiSig, _newMultiSig);
        multiSig = _newMultiSig;
    }
    
    /**
     * 转移 owner
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }
    
    /**
     * 接收 BNB
     */
    receive() external payable {}
}
