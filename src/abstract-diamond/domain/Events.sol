// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IDiamondCut} from "src/abstract-diamond/interfaces/IDiamondCut.sol";

library Events {
    event FacetVersionUpdated(
        bytes32 indexed facetId,
        string name,
        bytes32 commit,
        bytes32 fileHash
    );

    event RoleGranted(
        bytes32 indexed role,
        address indexed account,
        address indexed sender
    );

    event RoleRevoked(address indexed account, bytes32 indexed role);

    event DiamondCut(
        IDiamondCut.FacetCut[] _diamondCut,
        address _init,
        bytes _calldata
    );
}
