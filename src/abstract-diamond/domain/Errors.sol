// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

library Errors {
    error LibDiamond__IncorrectFacetAction();
    error LibDiamond__FacetCantBeAddressZero();
    error LibDiamond__NoSelectorsInFacetToCut();
    error LibDiamond__FunctionSelectorAlreadyExists(bytes4 selector);
    error LibDiamond__CantRemoveFunctionThatDoesNotExists();
    error LibDiamond__CantReplaceFunctionWithSameFunction();
    error LibDiamond__CantRemoveImmutableFunction();
    error LibDiamond__CantAddFunctionThatAlreadyExists(bytes4 selector);
    error LibDiamond__InitializationFunctionReverted(
        address _init,
        bytes _calldata
    );
    error LibDiamond__InitAddressHasNoCode();
    error LibDiamond__FunctionDoesNotExist(bytes4 selector);
    error LibDiamond__MetadataLengthMismatch(
        uint256 metadataLength,
        uint256 facetsLength
    );

    error LibDiamond__Unauthorized(address caller);
}
