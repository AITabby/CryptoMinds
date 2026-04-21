// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * CryptoMinds Adapter for Four.meme
 * ⚠️ 注意：此合约为参考设计，尚未部署到任何链上。仅用于展示集成思路，
 * 不能作为生产合约地址或真实支付入口使用。
 * 这是一个参考合约，展示如何将 Four.meme 项目数据接入 CryptoMinds 经济体系
 * Four.meme 可以调用此合约来：
 * 1. 注册新项目到 CryptoMinds 市场
 * 2. 支付分析费用给 CryptoMinds 专家
 * 3. 接收分析报告
 */
contract CryptoMindsAdapter {
    // 事件
    event ProjectRegistered(
        address indexed projectAddress,
        string projectName,
        string symbol,
        address indexed creator,
        uint256 timestamp
    );
    
    event AnalysisRequested(
        address indexed projectAddress,
        address indexed requester,
        uint256 fee,
        string analysisType,
        uint256 timestamp
    );
    
    event AnalysisCompleted(
        address indexed projectAddress,
        address indexed analyst,
        string reportCID,  // IPFS 或 Arweave 上的报告链接
        uint256 score,
        uint256 timestamp
    );
    
    // CryptoMinds 支付合约地址（占位符）
    // 部署前必须替换；当前仓库里没有可直接使用的生产地址。
    address public constant CRYPTO_MINDS_PAY = 0x...;
    
    // 项目信息结构
    struct Project {
        address projectAddress;
        string name;
        string symbol;
        address creator;
        uint256 registeredAt;
        bool isActive;
        uint256 totalAnalysisFeePaid;
        uint256 lastAnalysisScore;
    }
    
    // 项目映射
    mapping(address => Project) public projects;
    
    // 请求分析
    function requestAnalysis(
        address projectAddress,
        string memory analysisType,
        uint256 fee
    ) external payable {
        require(projects[projectAddress].isActive, "Project not registered");
        require(msg.value >= fee, "Insufficient fee");
        
        // 这里应该调用 CryptoMinds 支付合约
        // 简化为直接记录
        
        emit AnalysisRequested(
            projectAddress,
            msg.sender,
            fee,
            analysisType,
            block.timestamp
        );
    }
    
    // 注册项目（只能由 Four.meme 合约调用）
    function registerProject(
        address projectAddress,
        string memory name,
        string memory symbol,
        address creator
    ) external {
        require(msg.sender != address(0), "Invalid caller");
        
        projects[projectAddress] = Project({
            projectAddress: projectAddress,
            name: name,
            symbol: symbol,
            creator: creator,
            registeredAt: block.timestamp,
            isActive: true,
            totalAnalysisFeePaid: 0,
            lastAnalysisScore: 0
        });
        
        emit ProjectRegistered(projectAddress, name, symbol, creator, block.timestamp);
    }
    
    // 接收分析结果（由 CryptoMinds 专家调用）
    function submitAnalysisResult(
        address projectAddress,
        string memory reportCID,
        uint256 score
    ) external {
        require(msg.sender != address(0), "Invalid caller");
        
        require(projects[projectAddress].isActive, "Project not found");
        
        projects[projectAddress].lastAnalysisScore = score;
        
        emit AnalysisCompleted(projectAddress, msg.sender, reportCID, score, block.timestamp);
    }
    
    // 获取项目信息
    function getProjectInfo(address projectAddress) external view returns (
        string memory name,
        string memory symbol,
        address creator,
        uint256 registeredAt,
        uint256 lastScore
    ) {
        Project memory proj = projects[projectAddress];
        require(proj.isActive, "Project not found");
        
        return (
            proj.name,
            proj.symbol,
            proj.creator,
            proj.registeredAt,
            proj.lastAnalysisScore
        );
    }
}
