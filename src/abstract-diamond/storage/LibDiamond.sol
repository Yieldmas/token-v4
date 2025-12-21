// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/******************************************************************************\
* Author: Nick Mudge <nick@perfectabstractions.com> (https://twitter.com/mudgen)
* EIP-2535 Diamonds: https://eips.ethereum.org/EIPS/eip-2535
/******************************************************************************/
import {
    IDiamondCut
} from "src/abstract-diamond/interfaces/IDiamondCut.sol";
import {VersionTypes} from "src/abstract-diamond/domain/VersionTypes.sol";
import {
    LibFacetVersionStorage
} from "src/abstract-diamond/storage/LibFacetVersionStorage.sol";

import {Events} from "src/abstract-diamond/domain/Events.sol";
import {Errors} from "src/abstract-diamond/domain/Errors.sol";

// Remember to add the loupe functions from DiamondLoupeFacet to the diamond.
// The loupe functions are required by the EIP2535 Diamonds standard

library LibDiamond {
    // 32 bytes keccak hash of a string to use as a diamond storage location.
    bytes32 constant DIAMOND_STORAGE_POSITION =
        keccak256("diamond.standard.diamond.storage");

    bytes32 constant ADMIN = keccak256("ADMIN");
    bytes32 constant HOOK = keccak256("HOOK");

    struct FacetAddressAndPosition {
        address facetAddress;
        uint96 functionSelectorPosition; // position in facetFunctionSelectors.functionSelectors array
    }

    struct FacetFunctionSelectors {
        bytes4[] functionSelectors;
        uint256 facetAddressPosition; // position of facetAddress in facetAddresses array
    }

    struct DiamondStorage {
        // maps function selector to the facet address and
        // the position of the selector in the facetFunctionSelectors.selectors array
        mapping(bytes4 => FacetAddressAndPosition) selectorToFacetAndPosition;
        // maps facet addresses to function selectors
        mapping(address => FacetFunctionSelectors) facetFunctionSelectors;
        // facet addresses
        address[] facetAddresses;
        // Used to query if a contract implements an interface.
        // Used to implement ERC-165.
        mapping(bytes4 => bool) supportedInterfaces;
        // owner of the contract
        mapping(address => mapping(bytes32 => bool)) roles;
    }

    function diamondStorage()
        internal
        pure
        returns (DiamondStorage storage ds)
    {
        bytes32 position = DIAMOND_STORAGE_POSITION;
        // assigns struct storage slot to the storage position
        assembly {
            ds.slot := position
        }
    }

    function grantRole(address _user, bytes32 _role) internal {
        DiamondStorage storage ds = diamondStorage();
        ds.roles[_user][_role] = true;
        emit Events.RoleGranted(_role, _user, msg.sender);
    }

    function removeRole(address _user, bytes32 _role) internal {
        DiamondStorage storage ds = diamondStorage();
        ds.roles[_user][_role] = false;
        emit Events.RoleRevoked(_user, _role);
    }

    function hasRole(
        address _user,
        bytes32 _role
    ) internal view returns (bool) {
        DiamondStorage storage ds = diamondStorage();
        return ds.roles[_user][_role];
    }

    // Internal function version of diamondCut
    function diamondCut(
        IDiamondCut.FacetCut[] memory _diamondCut,
        address _init,
        bytes memory _calldata
    ) internal {
        (
            bytes memory initCalldata,
            VersionTypes.MetadataDto[] memory metas
        ) = abi.decode(_calldata, (bytes, VersionTypes.MetadataDto[]));

        uint256 facetsLen = _diamondCut.length;
        require(
            metas.length == facetsLen,
            Errors.LibDiamond__MetadataLengthMismatch(
                metas.length,
                facetsLen
            )
        );

        for (uint256 i; i < facetsLen; ) {
            IDiamondCut.FacetCut memory cut = _diamondCut[i];
            if (cut.action == IDiamondCut.FacetCutAction.Add) {
                addFunctions(cut.facetAddress, cut.functionSelectors);
            } else if (cut.action == IDiamondCut.FacetCutAction.Replace) {
                replaceFunctions(cut.facetAddress, cut.functionSelectors);
            } else if (cut.action == IDiamondCut.FacetCutAction.Remove) {
                removeFunctions(cut.facetAddress, cut.functionSelectors);
            } else {
                revert Errors.LibDiamond__IncorrectFacetAction();
            }

            // persist version info
            syncFacetVersion(cut.facetAddress, metas[i]);
            unchecked {
                ++i;
            }
        }

        emit Events.DiamondCut(_diamondCut, _init, initCalldata);
        initializeDiamondCut(_init, initCalldata);
    }

    function addFunctions(
        address _facetAddress,
        bytes4[] memory _functionSelectors
    ) internal {
        require(
            _functionSelectors.length > 0,
            Errors.LibDiamond__NoSelectorsInFacetToCut()
        );
        DiamondStorage storage ds = diamondStorage();
        require(
            _facetAddress != address(0),
            Errors.LibDiamond__FacetCantBeAddressZero()
        );
        uint96 selectorPosition = uint96(
            ds
                .facetFunctionSelectors[_facetAddress]
                .functionSelectors
                .length
        );

        // add new facet address if it does not exist
        if (selectorPosition == 0) {
            addFacet(ds, _facetAddress);
        }
        for (
            uint256 selectorIndex;
            selectorIndex < _functionSelectors.length;
            selectorIndex++
        ) {
            bytes4 selector = _functionSelectors[selectorIndex];
            address oldFacetAddress = ds
                .selectorToFacetAndPosition[selector]
                .facetAddress;
            require(
                oldFacetAddress == address(0),
                Errors.LibDiamond__CantAddFunctionThatAlreadyExists(
                    selector
                )
            );
            addFunction(ds, selector, selectorPosition, _facetAddress);
            selectorPosition++;
        }
    }

    function replaceFunctions(
        address _facetAddress,
        bytes4[] memory _functionSelectors
    ) internal {
        require(
            _functionSelectors.length > 0,
            Errors.LibDiamond__NoSelectorsInFacetToCut()
        );
        DiamondStorage storage ds = diamondStorage();
        require(
            _facetAddress != address(0),
            Errors.LibDiamond__FacetCantBeAddressZero()
        );
        uint96 selectorPosition = uint96(
            ds
                .facetFunctionSelectors[_facetAddress]
                .functionSelectors
                .length
        );
        // add new facet address if it does not exist
        if (selectorPosition == 0) {
            addFacet(ds, _facetAddress);
        }
        for (
            uint256 selectorIndex;
            selectorIndex < _functionSelectors.length;
            selectorIndex++
        ) {
            bytes4 selector = _functionSelectors[selectorIndex];
            address oldFacetAddress = ds
                .selectorToFacetAndPosition[selector]
                .facetAddress;
            require(
                oldFacetAddress != _facetAddress,
                Errors.LibDiamond__CantReplaceFunctionWithSameFunction()
            );
            removeFunction(ds, oldFacetAddress, selector);
            addFunction(ds, selector, selectorPosition, _facetAddress);
            selectorPosition++;
        }
    }

    function removeFunctions(
        address _facetAddress,
        bytes4[] memory _functionSelectors
    ) internal {
        require(
            _functionSelectors.length > 0,
            Errors.LibDiamond__NoSelectorsInFacetToCut()
        );
        DiamondStorage storage ds = diamondStorage();
        // if function does not exist then do nothing and return
        require(
            _facetAddress != address(0),
            Errors.LibDiamond__FacetCantBeAddressZero()
        );
        for (
            uint256 selectorIndex;
            selectorIndex < _functionSelectors.length;
            selectorIndex++
        ) {
            bytes4 selector = _functionSelectors[selectorIndex];
            address oldFacetAddress = ds
                .selectorToFacetAndPosition[selector]
                .facetAddress;
            removeFunction(ds, oldFacetAddress, selector);
        }
    }

    function addFacet(
        DiamondStorage storage ds,
        address _facetAddress
    ) internal {
        enforceHasContractCode(_facetAddress);
        ds.facetFunctionSelectors[_facetAddress].facetAddressPosition = ds
            .facetAddresses
            .length;
        ds.facetAddresses.push(_facetAddress);
    }

    function addFunction(
        DiamondStorage storage ds,
        bytes4 _selector,
        uint96 _selectorPosition,
        address _facetAddress
    ) internal {
        ds
            .selectorToFacetAndPosition[_selector]
            .functionSelectorPosition = _selectorPosition;
        ds.facetFunctionSelectors[_facetAddress].functionSelectors.push(
            _selector
        );
        ds
            .selectorToFacetAndPosition[_selector]
            .facetAddress = _facetAddress;
    }

    function removeFunction(
        DiamondStorage storage ds,
        address _facetAddress,
        bytes4 _selector
    ) internal {
        require(
            _facetAddress != address(0),
            Errors.LibDiamond__CantRemoveFunctionThatDoesNotExists()
        );
        // an immutable function is a function defined directly in a diamond
        require(
            _facetAddress != address(this),
            Errors.LibDiamond__CantRemoveImmutableFunction()
        );
        // replace selector with last selector, then delete last selector
        uint256 selectorPosition = ds
            .selectorToFacetAndPosition[_selector]
            .functionSelectorPosition;
        uint256 lastSelectorPosition = ds
            .facetFunctionSelectors[_facetAddress]
            .functionSelectors
            .length - 1;
        // if not the same then replace _selector with lastSelector
        if (selectorPosition != lastSelectorPosition) {
            bytes4 lastSelector = ds
                .facetFunctionSelectors[_facetAddress]
                .functionSelectors[lastSelectorPosition];
            ds.facetFunctionSelectors[_facetAddress].functionSelectors[
                selectorPosition
            ] = lastSelector;
            ds
                .selectorToFacetAndPosition[lastSelector] // forge-lint: disable-next-line(unsafe-typecast)
                .functionSelectorPosition = uint96(selectorPosition);
        }
        // delete the last selector
        ds.facetFunctionSelectors[_facetAddress].functionSelectors.pop();
        delete ds.selectorToFacetAndPosition[_selector];

        // if no more selectors for facet address then delete the facet address
        if (lastSelectorPosition == 0) {
            // replace facet address with last facet address and delete last facet address
            uint256 lastFacetAddressPosition = ds.facetAddresses.length -
                1;
            uint256 facetAddressPosition = ds
                .facetFunctionSelectors[_facetAddress]
                .facetAddressPosition;
            if (facetAddressPosition != lastFacetAddressPosition) {
                address lastFacetAddress = ds.facetAddresses[
                    lastFacetAddressPosition
                ];
                ds.facetAddresses[facetAddressPosition] = lastFacetAddress;
                ds
                    .facetFunctionSelectors[lastFacetAddress]
                    .facetAddressPosition = facetAddressPosition;
            }
            ds.facetAddresses.pop();
            delete ds
                .facetFunctionSelectors[_facetAddress]
                .facetAddressPosition;
        }
    }

    function initializeDiamondCut(
        address _init,
        bytes memory _calldata
    ) internal {
        if (_init == address(0)) {
            return;
        }
        enforceHasContractCode(_init);
        (bool success, bytes memory error) = _init.delegatecall(_calldata);
        if (!success) {
            if (error.length > 0) {
                // bubble up error
                /// @solidity memory-safe-assembly
                assembly {
                    let returndata_size := mload(error)
                    revert(add(32, error), returndata_size)
                }
            } else {
                revert Errors.LibDiamond__InitializationFunctionReverted(
                    _init,
                    _calldata
                );
            }
        }
    }

    function syncFacetVersion(
        address facetAddress,
        VersionTypes.MetadataDto memory metadata
    ) internal {
        if (facetAddress == address(0)) {
            return;
        }
        LibFacetVersionStorage.setFacetVersionByAddress(
            facetAddress,
            metadata
        );
    }

    function enforceHasContractCode(address _contract) internal view {
        uint256 contractSize;
        assembly {
            contractSize := extcodesize(_contract)
        }
        require(
            contractSize > 0,
            Errors.LibDiamond__InitAddressHasNoCode()
        );
    }
}
